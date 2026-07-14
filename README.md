# Kavi: a local voice assistant for Linux

Built for Linux Mint (X11), and built specifically to run well on old laptops. No GPU, no cloud, no problem: Kavi is designed to be light enough for hardware most projects have long written off.

Wispr Flow, but local. Press a hotkey, talk, and the text lands at your cursor. Press a different hotkey and talk to a local LLM instead. No cloud calls, no API keys, no network dependency at all.

## Why

Typing breaks focus for short things: quick notes, commands, chat. Voice doesn't. Kavi gives you that without sending audio anywhere.

## What it does

- **Dictation**: hold a hotkey, speak, release, and the transcript is typed at your cursor.
- **Chat**: a separate hotkey routes speech to a local LLM and streams the reply back.
- **Fully local**: speech-to-text (whisper.cpp), the LLM (llama.cpp), and text-to-speech (Piper, opt-in) all run on-device.
- **Runs as a service**: systemd `--user` units autostart everything at login.

## Quick start

```bash
cd voice-chat
./install.sh        # first time only (or after git pull) - sets up systemd services + CLI
kavi status          # check all 5 services are running (whisper, llama, kavi, xbindkeys, indicator)
kavi logs            # follow the daemon log

# Dictation: Right Ctrl (or Pause) - press once to start, press again to stop
# Chat: Menu key - press once to start, press again to stop, always routed to the LLM
```

## Hardware target

Kavi is built to run on modest, everyday hardware, not a workstation.

- **Minimum**: any x86_64 Linux machine, 8 GB RAM, CPU-only. Everything falls back to CPU and still works, just slower.
- **Recommended**: a discrete GPU with 4+ GB VRAM (Maxwell-generation or newer) speeds up STT and LLM inference noticeably.
- **Developed and tested on**: a 2015 Dell Inspiron 7559 (i7-6700HQ, GTX 960M 4 GB VRAM, 16 GB RAM, Linux Mint 22.3, PipeWire). If it's smooth there, it'll be smooth on most machines built in the last decade.
- Requires X11 (`xdotool`, `xbindkeys`). No Wayland support yet.

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

Full system diagrams (process topology, sequence flows, resource profile): [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Configuration

Kavi loads its tunable config from `brain/skills/kavi-voice-assistant.md` (YAML frontmatter): wake word, fuzzy match distance, VAD aggressiveness, silence thresholds. Edit the skill and restart Kavi, no code changes needed.

## Project layout

- `voice-chat/`: Kavi itself, the daemon, install script, systemd units, CLI (`kavi start|stop|status|logs`).
- `ARCHITECTURE.md`: diagrams for hotkey chain, process topology, dispatch logic, resource profile.
- `voice-chat/CLAUDE.md`: stack details and dev notes for this subproject.

## License

Private. Not for distribution.
