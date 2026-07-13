# CLAUDE.md — voice-chat project

## What this is

Voice-in, text-out chat with a local LLM (Qwen 2.5 1.5B via llama.cpp). Audio capture
via PipeWire (`pw-cat`) or ALSA (`arecord` fallback). Transcription via whisper.cpp
(ggml-base.en). All local. Zero network.

## Why this exists

Typing into the terminal takes focus. Talking doesn't. For short queries and quick
captures, voice chat reduces friction. Also: it's a stress test of the same stack
that powers the voice-enforcer (llama.cpp + CUDA SM 5.0 + Maxwell).

## Platform notes

- Linux Mint 22.3 with PipeWire 1.0.5 (PulseAudio compat layer)
- pw-cat is the primary capture method (PipeWire-native)
- arecord is the fallback if pw-cat is unavailable
- xdotool is NOT installed (skipping nerd-dictation)
- VOSK has known PipeWire issues (community documented)

## Stack

| Layer | Tool | Path |
|---|---|---|
| Audio capture | `pw-cat` or `arecord` | system |
| STT | whisper-cli (CUDA SM 5.0 build) | `/home/nidhi/learn/whisper.cpp/build-cuda/bin/whisper-cli` |
| LLM | llama-cli (CUDA SM 5.0 build) | `/home/nidhi/learn/llama.cpp/build-cuda/bin/llama-cli` |
| Whisper model | ggml-base.en.bin | `~/.cache/whisper.cpp/ggml-base.en.bin` |
| LLM model | Qwen 2.5 1.5B Q4_K_M | `~/.cache/llama.cpp/qwen2.5-1.5b-instruct-q4_k_m.gguf` |

## Files

- `scripts/chat.sh` — main wrapper
- `cache/` — temporary WAV files (gitignored)
- `models/` — symlinks to model files (gitignored)

## Don't

- Don't try nerd-dictation. xdotool isn't installed and VOSK is broken on PipeWire.
- Don't add network calls. Voice chat v0 is 100% local.
- Don't use a model larger than 2B for this. Memory ceiling is real.