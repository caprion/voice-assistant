# Voice Assistant

A local voice assistant for Linux, inspired by Wispr Flow. Hotkey activation, dictation at cursor, optional chat with local LLM.

Runs on modest hardware. No network calls during normal operation.

## What's here

- **`voice-enforcer/`** — fine-tuning pipeline for a writing-style cleanup model (Path C: training abandoned, base model ships instead)
- **`voice-chat/`** — Kavi, the working voice assistant (this is where the action is)
- **`STATE.md`** — comprehensive state, what's working, what's not, how to resume

## Quick start

```bash
cd voice-chat
./install.sh        # first time only (or after git pull) - sets up systemd services + CLI
kavi status          # check all 5 services are running (whisper, llama, kavi, xbindkeys, indicator)
kavi logs            # follow the daemon log

# Dictation: Right Ctrl (or Pause) - press once to start, press again to stop
# Chat: Menu key - press once to start, press again to stop, always routed to the LLM
```

Kavi autostarts at login via systemd `--user` services (no manual nohup needed). See `voice-chat/CLAUDE.md` for the manual/dev startup path.

## Architecture

```
[Right Ctrl] → xbindkeys → ~/.cache/kavi/trigger (flag file)        [dictation/wake-word cycle]
[Menu key]   → xbindkeys → ~/.cache/kavi/chat_trigger (flag file)   [forced chat cycle]
                                          ↓
[Kavi daemon] ← (polls flag files every 100ms)
    ↓
[Audio capture, Silero VAD] → recording ends on a second press of the same hotkey
    ↓                          (manual stop only - no auto-stop-on-silence, so pauses
    ↓                           mid-thought never cut you off)
[STT: whisper small.en via persistent whisper-server (HTTP), beam-size 5]
    ↓
[Transcript]
    ↓
[Smart dispatch]
    ├─ Menu-key press (forced chat) OR wake word "Kavi" fuzzy-matched (Right Ctrl path)
    │     → [LLM: Qwen 2.5 1.5B via persistent llama-server, streaming] → desktop notification (+ TTS if --tts)
    └─ Right Ctrl, no wake word → [xdotool type at cursor] (dictation)

[Floating state dot] ← polls ~/.cache/kavi/state (idle/listening/processing), draggable
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
