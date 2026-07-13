# CLAUDE.md — voice-chat project

## What this is

A local voice assistant (Kavi) that captures speech, transcribes with a local STT model, and either types at the cursor (dictation mode, the primary use case) or sends to a local LLM for chat. All inference local, zero network.

## Why it exists

Typing into the terminal takes focus. Talking doesn't. For short queries and quick captures, voice reduces friction. The Wispr Flow analog for a Linux CLI.

## Platform notes

- Linux Mint 22.3 with PipeWire 1.0.5 (PulseAudio compat layer)
- `pw-cat` is the primary capture method (PipeWire-native)
- `arecord` is the fallback if `pw-cat` is unavailable
- `xbindkeys` handles the hotkey (Print Screen / Right Ctrl) via flag file
- `xdotool` types into the active X11 window (dictation mode)
- VOSK has known PipeWire issues, so we use whisper.cpp / Parakeet instead

## Stack

| Layer | Tool | Path |
|---|---|---|
| Audio capture | `pw-cat` or `arecord` | system |
| STT (default) | `parakeet-cli` (CUDA SM 5.0) | `/home/nidhi/learn/whisper.cpp/build-cuda/bin/parakeet-cli` |
| STT (fallback) | `whisper-cli` (CUDA SM 5.0) | same dir |
| LLM | `llama-cli` (CUDA SM 5.0) | `/home/nidhi/learn/llama.cpp/build-cuda/bin/llama-cli` |
| TTS (opt-in) | piper (en_US-lessac-medium) | `~/.cache/piper/` |
| Text injection | `xdotool type` | system |
| Hotkey | `xbindkeys` → flag file | `~/.xbindkeysrc` |

## Models (current)

| Model | Path | Size |
|---|---|---|
| Parakeet TDT 0.6B v3 (default STT) | `~/.cache/parakeet/ggml-model.bin` | 1.2 GB |
| Whisper base.en (fallback) | `~/.cache/whisper.cpp/ggml-base.en.bin` | 140 MB |
| Qwen 2.5 1.5B Instruct Q4_K_M (LLM) | `~/.cache/llama.cpp/qwen2.5-1.5b-instruct-q4_k_m.gguf` | 1.07 GB |

## Files

- `scripts/kavi.py` — main voice assistant (270 lines, config from skill)
- `scripts/kavi-trigger.sh` — xbindkeys hotkey trigger
- `scripts/chat.sh` — legacy v0 (fixed 5s cuts, superseded)
- `scripts/venus.sh` — legacy wake-word prototype
- `cache/` — temporary WAV files (gitignored)
- `~/.xbindkeysrc` — hotkey bindings

## Hotkey bindings

Print Screen or Right Ctrl → `kavi-trigger.sh` → flag file → Kavi cycle.

## Modes

- **Hotkey mode (default)**: Print Screen triggers one record-transcribe-dispatch cycle.
- `--always-on`: continuously listening (heavier on CPU, opt-in).
- `--once`: run one cycle and exit (for testing).
- `--no-tts`: text-only response, no Piper playback.
- `--stt whisper`: use whisper base.en instead of Parakeet (lighter CPU, lower accuracy).

## Resource profile (typical cycle)

| Component | CPU peak | VRAM | Duration |
|---|---|---|---|
| VAD recording | low | 0 | until silence |
| Parakeet STT | ~100% (1 core) | 1.3 GB | 1.5-2 sec |
| Qwen LLM (if chat) | ~100% (1 core) | 1.3 GB | 3-5 sec |
| Piper TTS (if enabled) | low | 0 | 0.5-1 sec |
| xdotool type | low | 0 | <0.5 sec |

Total cycle (dictation only): ~1.5-2 sec.
Total cycle (chat, with TTS): ~5-9 sec.
Idle (waiting for hotkey): ~0 CPU, ~0 VRAM.

## Don't

- Don't try nerd-dictation. VOSK is broken on PipeWire, xdotool works.
- Don't add network calls. Voice chat is 100% local.
- Don't run always-on mode on this hardware without expecting fan noise.
- Don't enable TTS by default. It adds latency and audio device contention. Opt-in.
- Don't try to add llama-server / whisper-server streaming. Per-cycle subprocess is fine for the user's use case (dictation is the primary mode, latency is acceptable).

## Skill

Intelligence lives in `brain/skills/kavi-voice-assistant.md` (YAML frontmatter for tunable config). To change wake word, fuzzy threshold, VAD parameters, end-of-utterance silence: edit the skill, restart Kavi.

## Known issues

- Model reload per cycle (1-2 sec overhead). Persistent server would fix, but adds complexity. Not worth it for current use case.
- Parakeet at 100% CPU during inference. Fan noise during cycles. This is the cost of local STT. Smaller model (whisper tiny) is an option if noise is too disruptive.
- TTS uses Piper American English voice, doesn't match Indian English preference. Opt-in only.
- No streaming LLM response. Each cycle waits for full response. Could use llama-server streaming in future.
