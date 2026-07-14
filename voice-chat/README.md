# Voice Chat v0

Push-to-talk (well, "press Enter and talk for N seconds") voice chat into the terminal.
Fully local. Zero network calls.

## Pipeline

```
pw-cat (PipeWire mic capture)
  -> WAV file
  -> whisper-cli (transcribe)
  -> transcript text
  -> llama-cli (Qwen 1.5B respond)
  -> printed response
```

## Setup

### 1. Build whisper.cpp (CUDA SM 5.0)

```bash
cd $HOME/learn/whisper.cpp
mkdir build-cuda && cd build-cuda
cmake .. -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=50 -DCMAKE_BUILD_TYPE=Release -G Ninja
ninja
```

### 2. Download the Whisper base.en model

```bash
mkdir -p ~/.cache/whisper.cpp
cd ~/.cache/whisper.cpp
curl -sL "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin" -o ggml-base.en.bin
```

### 3. Qwen model

Already pulled by the voice-enforcer project at `~/.cache/llama.cpp/qwen2.5-1.5b-instruct-q4_k_m.gguf`.

## Usage

```bash
# Record 5 seconds, transcribe, respond
./scripts/chat.sh

# Record 8 seconds
./scripts/chat.sh 8

# Continuous mode (5-second cycles until Ctrl+C)
./scripts/chat.sh --continuous
```

## Acceptance bar

- Press Enter, speak 5-word command, response prints within 5 seconds.
- Zero network calls (verified with `ss -tnp` showing no new connections).
- 10 consecutive utterances succeed without crash.

## Known limitations

- No hotkey (must run the script). Future: F8 via `xbindkeys` or pynput.
- Fixed duration recording. Future: voice activity detection for natural stopping.
- English only. Hindi support requires a multilingual whisper model.
- No TTS read-back. Future: piper.
- No Claude API fallback. Future: optional integration.

## Related

- Voice enforcer project: `$HOME/learn/Code/voice-enforcer/`
- OOM postmortem (for the pre-flight pattern): `brain/pages/postmortems/2026-07-12-oom-hang.md`