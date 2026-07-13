#!/usr/bin/env python3
"""
kavi.py - Voice assistant harness. Intelligence lives in the kavi-voice-assistant
skill; this file is plumbing. See: brain/skills/kavi-voice-assistant.md
"""

import argparse
import difflib
import os
import re
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import frontmatter
import numpy as np
import sounddevice as sd
import webrtcvad

# --- Skill load (source of truth for tunable constants) ---
SKILL = frontmatter.load("/home/nidhi/learn/brain/skills/kavi-voice-assistant.md").get("config", {})
WAKE_WORD = SKILL["wake_word"]
FUZZY_THRESHOLD = SKILL["fuzzy_max_distance"]
SEARCH_TOKENS = SKILL["wake_word_search_tokens"]
VAD_LEVEL = SKILL["vad_aggressiveness"]
END_SILENCE_SEC = SKILL["end_silence_sec"]
BAIL_SEC = SKILL["bail_after_silence_sec"]
SAMPLE_RATE = SKILL["sample_rate"]
FRAME_MS = SKILL["frame_ms"]
MAX_UTTERANCE_SEC = SKILL["max_utterance_sec"]
GAIN_WARN_PCT = SKILL["gain_warning_threshold_pct"]
PARTIAL_INTERVAL = SKILL["partial_interval_sec"]
PARTIAL_MIN_SPEECH = SKILL["partial_min_speech_sec"]

FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
SILENCE_FRAMES = int(END_SILENCE_SEC * 1000 / FRAME_MS)
MAX_FRAMES = int(MAX_UTTERANCE_SEC * 1000 / FRAME_MS)
BAIL_FRAMES = int(BAIL_SEC * 1000 / FRAME_MS)
STOP_WORDS = {"stop", "exit", "quit", "bye", "goodbye", "done"}

# --- Paths (env-overridable plumbing, not intelligence) ---
CACHE = Path(__file__).resolve().parent.parent / "cache"; CACHE.mkdir(exist_ok=True)
TRIGGER = Path.home() / ".cache" / "kavi" / "trigger"; TRIGGER.parent.mkdir(exist_ok=True)
TOOLS = {
    "whisper_bin": os.environ.get("WHISPER_BIN", "/home/nidhi/learn/whisper.cpp/build-cuda/bin/whisper-cli"),
    "whisper_model": os.environ.get("WHISPER_MODEL", str(Path.home() / ".cache/whisper.cpp/ggml-base.en.bin")),
    "parakeet_bin": os.environ.get("PARAKEET_BIN", "/home/nidhi/learn/whisper.cpp/build-cuda/bin/parakeet-cli"),
    "parakeet_model": os.environ.get("PARAKEET_MODEL", str(Path.home() / ".cache/parakeet/ggml-model.bin")),
    "llama_bin": os.environ.get("LLAMA_BIN", "/home/nidhi/learn/llama.cpp/build-cuda/bin/llama-cli"),
    "llama_model": os.environ.get("LLAMA_MODEL", str(Path.home() / ".cache/llama.cpp/qwen2.5-1.5b-instruct-q4_k_m.gguf")),
    "piper_dir": os.environ.get("PIPER_VOICE_DIR", "/home/nidhi/learn/Code/voice-enforcer"),
    "piper_voice": os.environ.get("PIPER_VOICE", "en_US-lessac-medium"),
}


class Kavi:
    def __init__(self, stt: str, tts: bool):
        self.stt = stt
        self.tts = tts
        self.vad = webrtcvad.Vad(VAD_LEVEL)

    # --- Audio ---

    def record(self) -> np.ndarray | None:
        """Record until end-of-utterance (END_SILENCE_SEC of silence after speech)
        or BAIL_SEC silence bail. Streams audio in real-time but only transcribes
        on completion (model load is too heavy for true streaming on this hardware)."""
        chunks, speech, silent, total = [], False, 0, 0

        def cb(indata, *_):
            nonlocal silent, speech, total
            chunks.append(indata.copy().flatten())
            total += 1
            frame = chunks[-1][:FRAME_SAMPLES].astype(np.int16).tobytes()
            if len(frame) < FRAME_SAMPLES * 2:
                return
            if self.vad.is_speech(frame, SAMPLE_RATE):
                speech, silent = True, 0
            elif speech:
                silent += 1

        try:
            with sd.InputStream(SAMPLE_RATE, channels=1, dtype="int16",
                                blocksize=FRAME_SAMPLES, callback=cb):
                while total < MAX_FRAMES:
                    sd.sleep(FRAME_MS)
                    if speech and silent >= SILENCE_FRAMES:
                        break
                    if not speech and total >= BAIL_FRAMES:
                        return None
        except Exception as e:
            print(f"[kavi] audio: {e}", file=sys.stderr); return None
        if not chunks or not speech:
            return None
        audio = np.concatenate(chunks)
        if (audio.max() / 32767) * 100 < GAIN_WARN_PCT:
            print(f"[kavi] WARN: mic peak {audio.max()/327:.0f}% — boost gain")
        return audio

    # --- STT ---

    def transcribe(self, audio: np.ndarray) -> str:
        wav = CACHE / f"k_{int(time.time()*1000)}.wav"
        with wave.open(str(wav), "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.astype(np.int16).tobytes())
        try:
            if self.stt == "whisper":
                out = subprocess.run(
                    [TOOLS["whisper_bin"], "-m", TOOLS["whisper_model"], "-f", str(wav),
                     "--no-timestamps", "--print-special", "0"],
                    capture_output=True, text=True, timeout=30).stdout
                lines = [l.strip() for l in out.splitlines() if l.strip()]
                return lines[-1] if lines else ""
            out = subprocess.run(
                [TOOLS["parakeet_bin"], "-m", TOOLS["parakeet_model"], "-f", str(wav), "--no-prints"],
                capture_output=True, text=True, timeout=30).stdout
            skip = ("[", "ggml_cuda_init", "system_info", "read_audio", "main:", "parakeet_", "Successfully")
            for line in out.splitlines():
                line = line.strip()
                if line and not line.startswith(skip):
                    return line.replace("▁", " ").strip()
            return ""
        except Exception as e:
            print(f"[kavi] stt: {e}", file=sys.stderr); return ""
        finally:
            wav.unlink(missing_ok=True)

    # --- Wake word (fuzzy match) ---

    @staticmethod
    def _word_distance(a: str, b: str) -> int:
        """Levenshtein distance via dynamic programming."""
        if len(a) < len(b):
            a, b = b, a
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a):
            curr = [i + 1]
            for j, cb in enumerate(b):
                curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
            prev = curr
        return prev[-1]

    def parse_wake_word(self, transcript: str) -> tuple[bool, str]:
        """Fuzzy match WAKE_WORD within first SEARCH_TOKENS tokens. See skill for why."""
        tokens = [t.lower() for t in re.split(r"[\s,.\?!]+", transcript.strip()) if t]
        for i, tok in enumerate(tokens[:SEARCH_TOKENS]):
            if self._word_distance(tok, WAKE_WORD) <= FUZZY_THRESHOLD:
                rest = " ".join(tokens[i + 1:]).strip()
                if rest.lower() in STOP_WORDS:
                    return True, "__EXIT__"
                return True, rest
        return False, transcript

    # --- Actions ---

    def type_at_cursor(self, text: str) -> None:
        if not text:
            return
        try:
            time.sleep(0.3)
            subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "5", text], check=True, timeout=30)
            subprocess.run(["xdotool", "type", " "], check=True, timeout=5)
        except Exception as e:
            print(f"[kavi] xdotool: {e}", file=sys.stderr)

    def ask_qwen(self, prompt: str) -> str:
        try:
            out = subprocess.run(
                [TOOLS["llama_bin"], "-m", TOOLS["llama_model"], "-p", prompt,
                 "-n", "256", "-c", "2048", "--temp", "0.7", "-ngl", "999"],
                capture_output=True, text=True, timeout=60).stdout
            return "\n".join(l for l in out.splitlines()
                             if l.strip() and l.strip() != "> EOF by user").strip()
        except Exception as e:
            print(f"[kavi] qwen: {e}", file=sys.stderr); return ""

    def speak(self, text: str) -> None:
        if not self.tts or not text:
            return
        try:
            from piper import PiperVoice, SynthesisConfig
            wav = CACHE / "kavi_tts.wav"
            voice = PiperVoice.load(f'{TOOLS["piper_dir"]}/{TOOLS["piper_voice"]}.onnx',
                                    config_path=f'{TOOLS["piper_dir"]}/{TOOLS["piper_voice"]}.onnx.json')
            with wave.open(str(wav), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(voice.config.sample_rate)
                for chunk in voice.synthesize(SynthesisConfig(), text):
                    wf.writeframes(chunk.audio_int16_bytes)
            subprocess.run(["pw-play", str(wav)], capture_output=True, timeout=60)
        except Exception as e:
            print(f"[kavi] tts: {e}", file=sys.stderr)

    # --- Cycle + main loops ---

    def run_cycle(self) -> str | None:
        """One record-transcribe-dispatch cycle. Returns 'exit' on stop command."""
        print("[kavi] listening...")
        audio = self.record()
        if audio is None:
            print("[kavi] (no speech)"); return None
        transcript = self.transcribe(audio)
        if not transcript:
            print("[kavi] (empty)"); return None
        print(f"[kavi] heard: {transcript}")

        # Smart dispatch: wake word -> chat; otherwise -> dictation at cursor
        matched, command = self.parse_wake_word(transcript)
        if matched:
            if command == "__EXIT__":
                return "exit"
            print(f"[kavi] cmd: {command}")
            print("[kavi] thinking...")
            response = self.ask_qwen(command)
            print(f"[kavi] {response}")
            if self.tts:
                self.speak(response)
            return None
        print(f"[kavi] typing: {transcript}")
        self.type_at_cursor(transcript)

    def watch_trigger(self) -> None:
        """Print Screen hotkey mode (--trigger flag)."""
        print(f"[kavi] mode=trigger  stt={self.stt}  tts={self.tts}")
        print(f"[kavi] waiting for Print Screen hotkey. Ctrl+C to exit.")
        TRIGGER.unlink(missing_ok=True)
        try:
            while True:
                if TRIGGER.exists():
                    TRIGGER.unlink()
                    print("\n[kavi] cycle")
                    if self.run_cycle() == "exit":
                        break
                    print("[kavi] ready")
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n[kavi] Ctrl+C, exiting")

    def run_continuously(self) -> None:
        """Always-on mode (default). VAD segments speech, smart dispatch per utterance.
        Partial transcripts appear in the log every PARTIAL_INTERVAL_SEC during speech."""
        print(f"[kavi] mode=always-on  stt={self.stt}  tts={self.tts}")
        print(f"[kavi] listening. Say '{WAKE_WORD}' for chat, anything else for dictation. Ctrl+C to exit.")
        print(f"[kavi] partials every {PARTIAL_INTERVAL}s, end-of-utterance after {END_SILENCE_SEC}s silence")
        try:
            cycle = 0
            while True:
                cycle += 1
                print(f"\n[kavi] cycle {cycle}")
                if self.run_cycle() == "exit":
                    break
        except KeyboardInterrupt:
            print("\n[kavi] Ctrl+C, exiting")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stt", choices=["whisper", "parakeet"], default="parakeet")
    parser.add_argument("--no-tts", action="store_true")
    parser.add_argument("--always-on", action="store_true",
                        help="always-listening mode (default: Print Screen hotkey)")
    parser.add_argument("--once", action="store_true", help="one cycle then exit")
    args = parser.parse_args()

    kavi = Kavi(stt=args.stt, tts=not args.no_tts)
    if args.once:
        kavi.run_cycle()
    elif args.always_on:
        kavi.run_continuously()
    else:
        kavi.watch_trigger()


if __name__ == "__main__":
    main()