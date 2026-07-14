#!/usr/bin/env python3
"""
kavi.py - Voice assistant harness. Intelligence lives in config/kavi-config.md;
this file is plumbing.
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
import onnxruntime as ort
import sounddevice as sd

# --- Skill load (source of truth for tunable constants) ---
SKILL_PATH = os.environ.get("KAVI_SKILL_PATH", str(Path(__file__).resolve().parent.parent / "config" / "kavi-config.md"))
SKILL = frontmatter.load(SKILL_PATH).get("config", {})
WAKE_WORD = SKILL["wake_word"]
FUZZY_THRESHOLD = SKILL["fuzzy_max_distance"]
SEARCH_TOKENS = SKILL["wake_word_search_tokens"]
END_SILENCE_SEC = SKILL["end_silence_sec"]  # vestigial: auto-stop-on-silence removed 2026-07-14, manual stop only
BAIL_SEC = SKILL["bail_after_silence_sec"]
SAMPLE_RATE = SKILL["sample_rate"]
FRAME_MS = SKILL["frame_ms"]
MAX_UTTERANCE_SEC = SKILL["max_utterance_sec"]
GAIN_WARN_PCT = SKILL["gain_warning_threshold_pct"]
PARTIAL_INTERVAL = SKILL["partial_interval_sec"]
PARTIAL_MIN_SPEECH = SKILL["partial_min_speech_sec"]

FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
MAX_FRAMES = int(MAX_UTTERANCE_SEC * 1000 / FRAME_MS)
BAIL_FRAMES = int(BAIL_SEC * 1000 / FRAME_MS)
STOP_WORDS = {"stop", "exit", "quit", "bye", "goodbye", "done"}

# --- Paths (env-overridable plumbing, not intelligence) ---
CACHE = Path(__file__).resolve().parent.parent / "cache"; CACHE.mkdir(exist_ok=True)
TRIGGER = Path.home() / ".cache" / "kavi" / "trigger"; TRIGGER.parent.mkdir(exist_ok=True)
CHAT_TRIGGER = Path.home() / ".cache" / "kavi" / "chat_trigger"  # separate hotkey: force chat mode, skip wake-word matching
STATE_FILE = Path.home() / ".cache" / "kavi" / "state"  # polled by the tray/dot indicator (idle|listening|processing)
TOOLS = {
    "whisper_bin": os.environ.get("WHISPER_BIN", str(Path.home() / "learn/whisper.cpp/build-cuda/bin/whisper-cli")),
    "whisper_model": os.environ.get("WHISPER_MODEL", str(Path.home() / ".cache/whisper.cpp/ggml-base.en.bin")),
    "parakeet_bin": os.environ.get("PARAKEET_BIN", str(Path.home() / "learn/whisper.cpp/build-cuda/bin/parakeet-cli")),
    "parakeet_model": os.environ.get("PARAKEET_MODEL", str(Path.home() / ".cache/parakeet/ggml-model.bin")),
    "llama_bin": os.environ.get("LLAMA_BIN", str(Path.home() / "learn/llama.cpp/build-cuda/bin/llama-cli")),
    "llama_model": os.environ.get("LLAMA_MODEL", str(Path.home() / ".cache/llama.cpp/qwen2.5-1.5b-instruct-q4_k_m.gguf")),
    "piper_dir": os.environ.get("PIPER_VOICE_DIR", str(Path.home() / "learn/Code/voice-enforcer")),
    "piper_voice": os.environ.get("PIPER_VOICE", "en_US-lessac-medium"),
}
WHISPER_SERVER_URL = os.environ.get("WHISPER_SERVER_URL", "http://127.0.0.1:8090/inference")
LLAMA_SERVER_URL = os.environ.get(
    "LLAMA_SERVER_URL",
    f"http://{os.environ.get('LLAMA_SERVER_HOST', '127.0.0.1')}:{os.environ.get('LLAMA_SERVER_PORT', '8081')}/v1/chat/completions")
SILERO_VAD_PATH = os.environ.get("SILERO_VAD_PATH", str(Path.home() / ".cache/silero-vad/silero_vad.onnx"))
SILERO_VAD_THRESHOLD = float(os.environ.get("SILERO_VAD_THRESHOLD", "0.5"))
EDIT_PHRASES = ("scratch that", "delete that")
CORRECTIONS_PATH = Path(os.environ.get(
    "KAVI_CORRECTIONS_PATH",
    str(Path(__file__).resolve().parent.parent / "config" / "corrections.json")))


def load_corrections() -> dict[str, str]:
    """Reload from disk on every call (cheap, tiny file) so `kavi correct` entries
    take effect immediately without restarting the daemon."""
    try:
        import json
        with open(CORRECTIONS_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def apply_corrections(text: str) -> str:
    """Deterministic case-insensitive whole-phrase substitution. No LLM, no
    latency, no risk of dropping or inventing content - worst case an entry is
    wrong and the original mis-hearing stays, exactly as before this existed.
    Longest phrases first so multi-word entries win over single-word substrings."""
    corrections = load_corrections()
    if not corrections:
        return text
    for wrong in sorted(corrections, key=len, reverse=True):
        right = corrections[wrong]
        pattern = re.compile(re.escape(wrong), re.IGNORECASE)
        text = pattern.sub(right, text)
    return text


_EDIT_PATTERN = re.compile(r"\b(" + "|".join(re.escape(p) for p in EDIT_PHRASES) + r")\b", re.IGNORECASE)


def apply_edit_commands(text: str) -> str:
    """Mid-utterance verbal edit: say 'scratch that' or 'delete that' anywhere
    in a single dictation/chat cycle and everything up to and including the
    last occurrence is discarded, keeping only what follows. Nothing after
    the last marker means the whole utterance is discarded (redo the cycle
    by pressing the hotkey again). Only affects the current cycle's own
    transcript - it does not reach back and erase text already typed from a
    previous cycle."""
    matches = list(_EDIT_PATTERN.finditer(text))
    if not matches:
        return text
    return text[matches[-1].end():].strip()


class SileroVAD:
    """Neural VAD (onnxruntime, ~2MB model) - replaces webrtcvad.

    webrtcvad (classic energy/spectral heuristics) was measured flagging
    64-99% of pure ambient laptop-fan noise as "speech" on this machine,
    which meant recording never detected true silence and ran to the
    30s hard cap on almost every cycle. Silero (a small RNN trained on
    real speech/non-speech) measured 0% false positives on the same
    ambient noise sample and 69% mean / up to 100% confidence on known
    real speech (validated against whisper.cpp's jfk.wav sample).
    CPU-only, single frame ~1-2ms - negligible cost.

    IMPORTANT: matches the official silero-vad ONNX calling convention
    (see silero-vad's utils_vad.py OnnxWrapper) - each inference call
    needs a 64-sample "context" (the tail of the previous chunk)
    prepended to the new 512-sample chunk, giving a 576-sample input.
    Skipping this context prepend (an earlier version of this code did)
    silently produces near-zero probability for all audio, real speech
    included - it doesn't error, it just never detects anything.
    Requires exactly 512 new samples per call at 16kHz (frame_ms: 32 in
    the skill config produces this frame size - see FRAME_SAMPLES).
    """

    NUM_SAMPLES = 512   # required chunk size at 16kHz (256 at 8kHz, unused here)
    CONTEXT_SIZE = 64    # required context prefix size at 16kHz (32 at 8kHz)

    def __init__(self, model_path: str = SILERO_VAD_PATH, threshold: float = SILERO_VAD_THRESHOLD):
        self.sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, self.CONTEXT_SIZE), dtype=np.float32)
        self.threshold = threshold
        self.last_prob = 0.0

    def is_speech(self, frame_bytes: bytes, sample_rate: int) -> bool:
        pcm = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        frame = pcm.reshape(1, -1)
        if frame.shape[1] != self.NUM_SAMPLES:
            # Caller passed a frame size that doesn't match Silero's fixed chunking -
            # pad/truncate defensively rather than crash the whole daemon.
            frame = np.resize(frame, (1, self.NUM_SAMPLES))
        x = np.concatenate([self.context, frame], axis=1)
        out, self.state = self.sess.run(
            None, {"input": x, "state": self.state, "sr": np.array(sample_rate, dtype=np.int64)})
        self.context = x[:, -self.CONTEXT_SIZE:]
        self.last_prob = float(out[0][0])
        return self.last_prob > self.threshold


class Kavi:
    def __init__(self, stt: str, tts: bool):
        self.stt = stt
        self.tts = tts
        self.vad = SileroVAD()
        self.busy = False  # mutex: only one cycle at a time (Kavi is single-threaded)
        # Threading model: Kavi is single-threaded. Each cycle is atomic.
        # llama-server runs in a separate process and handles its own concurrency
        # via its slot system. No threads spawned in Kavi for streaming LLM;
        # httpx.stream is synchronous (read chunks as they arrive, no background).
        # The mutex above prevents a second hotkey press from firing a second
        # cycle while the first is still running.

    @staticmethod
    def notify(title: str, message: str, urgency: str = "low") -> None:
        """Desktop notification so Kavi is usable without a terminal open.
        Silently no-ops if notify-send is missing (headless/CI environments)."""
        try:
            subprocess.run(
                ["notify-send", "-a", "Kavi", "-u", urgency, "-t", "4000", title, message[:200]],
                capture_output=True, timeout=3)
        except Exception:
            pass

    @staticmethod
    def set_state(state: str) -> None:
        """Write current state (idle|listening|processing) for the floating dot
        indicator (kavi-indicator.py) to poll. Best-effort: a missing/unreadable
        cache dir must never break the actual voice pipeline."""
        try:
            STATE_FILE.write_text(state)
        except Exception:
            pass

    # --- Audio ---

    def record(self, stop_trigger: Path) -> np.ndarray | None:
        """Record until a second press of stop_trigger (manual stop - you control
        exactly when it ends, so pauses/thinking mid-sentence never cut you off),
        or BAIL_SEC silence bail if no speech was ever detected (accidental press
        safety net), or MAX_FRAMES hard cap. Streams audio in real-time but only
        transcribes on completion (model load too heavy for true streaming here)."""
        chunks, speech, silent, total = [], False, 0, 0
        debug = os.environ.get("KAVI_VAD_DEBUG") == "1"
        max_prob_seen = 0.0

        def cb(indata, *_):
            nonlocal silent, speech, total, max_prob_seen
            chunks.append(indata.copy().flatten())
            total += 1
            frame = chunks[-1][:FRAME_SAMPLES].astype(np.int16).tobytes()
            if len(frame) < FRAME_SAMPLES * 2:
                return
            is_sp = self.vad.is_speech(frame, SAMPLE_RATE)
            max_prob_seen = max(max_prob_seen, self.vad.last_prob)
            if debug:
                print(f"[kavi] vad_prob={self.vad.last_prob:.3f}", file=sys.stderr)
            if is_sp:
                speech, silent = True, 0
            elif speech:
                silent += 1

        try:
            with sd.InputStream(SAMPLE_RATE, channels=1, dtype="int16",
                                blocksize=FRAME_SAMPLES, callback=cb):
                while total < MAX_FRAMES:
                    sd.sleep(FRAME_MS)
                    if stop_trigger.exists():
                        stop_trigger.unlink()
                        print("[kavi] manual stop")
                        break
                    if not speech and total >= BAIL_FRAMES:
                        if debug:
                            print(f"[kavi] bailed, max_prob_seen={max_prob_seen:.3f}", file=sys.stderr)
                        return None
        except Exception as e:
            print(f"[kavi] audio: {e}", file=sys.stderr); return None
        if not chunks or not speech:
            return None
        audio = np.concatenate(chunks)
        if (audio.max() / 32767) * 100 < GAIN_WARN_PCT:
            pct = (audio.max() / 32767) * 100
            print(f"[kavi] WARN: mic peak {pct:.0f}% — boost gain")
            self.notify("Kavi: low mic gain", f"Peak {pct:.0f}% of max — consider boosting input gain.")
        return audio

    # --- STT ---

    def _transcribe_whisper_server(self, wav: Path) -> str | None:
        """Try the persistent whisper-server first (no per-cycle model reload).
        Returns None on any failure so the caller can fall back to subprocess."""
        try:
            import httpx
            with open(wav, "rb") as f:
                r = httpx.post(WHISPER_SERVER_URL,
                                files={"file": ("audio.wav", f, "audio/wav")},
                                data={"response_format": "text"}, timeout=15)
            if r.status_code == 200:
                return r.text.strip()
        except Exception as e:
            print(f"[kavi] whisper-server unreachable, falling back to subprocess: {e}", file=sys.stderr)
            self.notify("Kavi: STT server down", "whisper-server unreachable, using slower subprocess fallback.", urgency="normal")
        return None

    def transcribe(self, audio: np.ndarray) -> str:
        wav = CACHE / f"k_{int(time.time()*1000)}.wav"
        with wave.open(str(wav), "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.astype(np.int16).tobytes())
        try:
            if self.stt == "whisper":
                text = self._transcribe_whisper_server(wav)
                if text is not None:
                    return text
                # Fallback: per-cycle subprocess (server down / not started)
                out = subprocess.run(
                    ["nice", "-n", "10", TOOLS["whisper_bin"], "-m", TOOLS["whisper_model"], "-f", str(wav),
                     "--no-timestamps", "--print-special", "0"],
                    capture_output=True, text=True, timeout=30).stdout
                lines = [l.strip() for l in out.splitlines() if l.strip()]
                return lines[-1] if lines else ""
            # Parakeet: no persistent server available for this model, always subprocess
            out = subprocess.run(
                ["nice", "-n", "10", TOOLS["parakeet_bin"], "-m", TOOLS["parakeet_model"], "-f", str(wav), "--no-prints"],
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
        """Fuzzy match WAKE_WORD within transcript. Searches all tokens by default
        (so 'Hey, Kavi, are you there?' still matches Kavi at position 3).
        Set wake_word_search_all=false in skill to limit to first SEARCH_TOKENS."""
        text = transcript.strip()
        tokens = [t.lower() for t in re.split(r"[\s,.\?!]+", text) if t]
        search_all = SKILL.get("wake_word_search_all", True)
        search_tokens = tokens if search_all else tokens[:SEARCH_TOKENS]
        for i, tok in enumerate(search_tokens):
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
            subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "5", text], check=True, timeout=30)
            subprocess.run(["xdotool", "type", " "], check=True, timeout=5)
        except Exception as e:
            print(f"[kavi] xdotool: {e}", file=sys.stderr)

    def ask_qwen(self, prompt: str) -> str:
        """Stream from llama-server (persistent model, fast first-token). Fallback to subprocess."""
        url = LLAMA_SERVER_URL
        payload = {
            "model": "Qwen2.5-1.5B-Instruct",
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "max_tokens": 256,
            "temperature": 0.7,
        }
        full = []
        try:
            import httpx
            with httpx.stream("POST", url, json=payload, timeout=60) as r:
                if r.status_code == 200:
                    for line in r.iter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data.strip() == "[DONE]":
                                break
                            try:
                                chunk = __import__("json").loads(data)
                                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta:
                                    print(delta, end="", flush=True)
                                    full.append(delta)
                            except __import__("json").JSONDecodeError:
                                pass
                    print()  # newline after stream
                    return "".join(full).strip()
        except Exception:
            pass  # fall through to subprocess

        # Fallback: subprocess llama-cli (no streaming, slower)
        try:
            out = subprocess.run(
                ["nice", "-n", "10", TOOLS["llama_bin"], "-m", TOOLS["llama_model"], "-p", prompt,
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

    def run_cycle(self, force_chat: bool = False) -> str | None:
        """One record-transcribe-dispatch cycle. Returns 'exit' on stop command.
        force_chat=True (Menu key hotkey) skips wake-word matching entirely and
        routes the whole utterance to chat - no need to say "kavi" first.
        Press the same hotkey again mid-recording to manually stop (instead of
        waiting for VAD silence detection - useful for longer, multi-pause speech)."""
        print("[kavi] listening...")
        self.set_state("listening")
        stop_trigger = CHAT_TRIGGER if force_chat else TRIGGER
        audio = self.record(stop_trigger)
        self.set_state("processing")
        try:
            if audio is None:
                print("[kavi] (no speech)"); return None
            transcript = self.transcribe(audio)
            if not transcript:
                print("[kavi] (empty)"); return None
            # Strip whisper's special tokens (appended to most outputs, not actual garbage)
            for tok in ("<|endoftext|>", "<|notimestamps|>"):
                transcript = transcript.replace(tok, "").strip()
            # Filter actual garbage: parenthesized/bracketed noise tags, very short
            stripped = transcript.strip()
            if (stripped.startswith("(") and stripped.endswith(")")) or \
               (stripped.startswith("[") and stripped.endswith("]")):
                print(f"[kavi] (garbage: noise) {stripped[:40]}")
                return None
            if len(stripped) < 3:
                print(f"[kavi] (garbage: too short) {stripped}")
                return None
            edited = apply_edit_commands(transcript)
            if edited != transcript:
                if not edited:
                    print(f"[kavi] heard: {transcript}")
                    print("[kavi] edit: 'scratch that'/'delete that' -> discarding whole utterance")
                    return None
                print(f"[kavi] heard: {transcript}  -> after edit: {edited}")
                transcript = edited
            corrected = apply_corrections(transcript)
            if corrected != transcript:
                print(f"[kavi] heard: {transcript}  -> corrected: {corrected}")
                transcript = corrected
            else:
                print(f"[kavi] heard: {transcript}")

            # Smart dispatch: force_chat (dedicated hotkey) always goes to chat.
            # Otherwise: wake word -> chat; anything else -> dictation at cursor.
            if force_chat:
                matched, command = True, transcript
            else:
                matched, command = self.parse_wake_word(transcript)
            if matched:
                if command == "__EXIT__":
                    return "exit"
                print(f"[kavi] cmd: {command}")
                print("[kavi] thinking...")
                response = self.ask_qwen(command)
                print(f"[kavi] {response}")
                self.notify(f"Kavi: {command[:40]}", response or "(no response)")
                if self.tts:
                    self.speak(response)
                return None
            else:
                print(f"[kavi] typing: {transcript}")
                self.type_at_cursor(transcript)
                return None
        finally:
            self.set_state("idle")

    def watch_trigger(self) -> None:
        """Print Screen hotkey mode (default). Cooldown between cycles lets the system breathe.
        Mutex prevents second press from firing concurrent cycle.
        TRIGGER (Right Ctrl/Pause) -> dictation-or-wake-word cycle.
        CHAT_TRIGGER (Menu key) -> forced chat cycle, no wake word needed."""
        print(f"[kavi] mode=trigger  stt={self.stt}  tts={self.tts}")
        print(f"[kavi] waiting for Right Ctrl (dictation) or Menu key (chat). Ctrl+C to exit.")
        TRIGGER.unlink(missing_ok=True)
        CHAT_TRIGGER.unlink(missing_ok=True)
        self.set_state("idle")
        try:
            while True:
                if TRIGGER.exists() and not self.busy:
                    TRIGGER.unlink()
                    print("\n[kavi] cycle")
                    self.busy = True
                    try:
                        if self.run_cycle() == "exit":
                            break
                    finally:
                        self.busy = False
                    print("[kavi] ready")
                    time.sleep(0.2)  # cooldown: let CPU/GPU settle
                elif CHAT_TRIGGER.exists() and not self.busy:
                    CHAT_TRIGGER.unlink()
                    print("\n[kavi] chat cycle")
                    self.busy = True
                    try:
                        if self.run_cycle(force_chat=True) == "exit":
                            break
                    finally:
                        self.busy = False
                    print("[kavi] ready")
                    time.sleep(0.2)  # cooldown: let CPU/GPU settle
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n[kavi] Ctrl+C, exiting")

    def run_continuously(self) -> None:
        """Always-on mode (--always-on flag). Heavier on CPU. Use only on capable hardware."""
        print(f"[kavi] mode=always-on  stt={self.stt}  tts={self.tts}")
        print(f"[kavi] listening. Say '{WAKE_WORD}' for chat, anything else for dictation. Ctrl+C to exit.")
        try:
            cycle = 0
            while True:
                cycle += 1
                print(f"\n[kavi] cycle {cycle}")
                if self.run_cycle() == "exit":
                    break
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("\n[kavi] Ctrl+C, exiting")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stt", choices=["whisper", "parakeet"], default="whisper",
                        help="STT engine. Default: whisper (lighter CPU). Parakeet is more accurate but heavier.")
    parser.add_argument("--tts", action="store_true",
                        help="enable Piper TTS reply in chat mode (default: text only)")
    parser.add_argument("--always-on", action="store_true",
                        help="always-listening mode (default: Print Screen hotkey)")
    parser.add_argument("--once", action="store_true", help="run one cycle then exit")
    args = parser.parse_args()

    kavi = Kavi(stt=args.stt, tts=args.tts)
    if args.once:
        kavi.run_cycle()
    elif args.always_on:
        kavi.run_continuously()
    else:
        kavi.watch_trigger()


if __name__ == "__main__":
    main()