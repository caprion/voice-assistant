# Voice Assistant

A local voice assistant for Linux, inspired by Wispr Flow. Hotkey activation, dictation at cursor, optional chat with local LLM.

Runs on modest hardware. No network calls during normal operation.

## What's here

- **`voice-enforcer/`** — fine-tuning pipeline for a writing-style cleanup model (Path C: training abandoned, base model ships instead)
- **`voice-chat/`** — Kavi, the working voice assistant (this is where the action is)
- **`STATE.md`** — comprehensive state, what's working, what's not, how to resume

## Quick start

```bash
# Activate venv (created during initial setup)
cd voice-chat
source ../voice-enforcer/.venv/bin/activate

# Start Kavi (hotkey mode)
nohup python3 -u scripts/kavi.py > /tmp/kavi.log 2>&1 &
disown

# Trigger: Print Screen or Right Ctrl (configured in ~/.xbindkeysrc)
# Watch log
tail -f /tmp/kavi.log
```

## Architecture

```
[Print Screen] → xbindkeys → ~/.cache/kavi/trigger (flag file)
                                          ↓
[Kavi daemon] ← (polls flag every 100ms)
    ↓
[Audio capture with VAD] → 0.8s silence = end of utterance
    ↓
[STT: Parakeet TDT 0.6B via whisper.cpp]
    ↓
[Transcript]
    ↓
[Smart dispatch]
    ├─ wake word "Kavi" detected → [LLM: Qwen 2.5 1.5B] → [TTS: piper] → speaker
    └─ no wake word → [xdotool type at cursor] (dictation)
```

## Hardware target

- 2015 Dell Inspiron 7559
- GTX 960M (Maxwell SM 5.0, 4 GB VRAM)
- 16 GB RAM
- Linux Mint 22.3 (PipeWire 1.0.5)
- Tested on X11 (xdotool, xbindkeys work natively)

## Skills (intelligence layer)

See `brain/skills/` in the parent repo. Five skills written for this project:

- `kavi-voice-assistant.md` — wake word, VAD, fuzzy match, mode dispatch
- `voice-chat-cli-platform.md` — PipeWire, xbindkeys, xdotool on Linux Mint
- `local-stt-comparison-2026.md` — whisper.cpp vs Parakeet TDT
- `maxwell-cuda-constraints.md` — CUDA build, PyTorch pinning, OOM on 4 GB
- `local-llm-finetune-2026.md` — Path A/B/C decision tree

Kavi.py loads config from `kavi-voice-assistant.md` YAML frontmatter. Tune behavior by editing the skill, not the Python.

## See also

- `STATE.md` — full state, file map, open work, decisions
- `/home/nidhi/learn/brain/pages/projects/voice-enforcer.md` — project state in brain
- `/home/nidhi/learn/brain/pages/postmortems/2026-07-12-oom-hang.md` — original OOM postmortem

## License

Private. Not for distribution.
