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
| STT (default) | `whisper-server` (persistent, GPU, base.en) | `127.0.0.1:8090`, started by `scripts/start-whisper-server.sh` |
| STT (fallback) | `whisper-cli` subprocess if server unreachable | `$HOME/learn/whisper.cpp/build-cuda/bin/whisper-cli` |
| STT (accuracy alt) | `parakeet-cli` subprocess (`--stt parakeet`, no server support, per-cycle reload) | same dir |
| LLM | `llama-server` (persistent, CPU, streaming) | `127.0.0.1:8081`, `-ngl 0 --threads 3 --parallel 1` |
| LLM (fallback) | `llama-cli` subprocess if server unreachable | `$HOME/learn/llama.cpp/build-cuda/bin/llama-cli` |
| TTS (opt-in via `--tts`) | piper (en_US-lessac-medium) | `~/.cache/piper/` |
| Text injection | `xdotool type` | system |
| Hotkey | `xbindkeys` → flag file | `~/.xbindkeysrc` |

## Models (current)

| Model | Path | Size |
|---|---|---|
| Whisper base.en (default STT, served warm) | `~/.cache/whisper.cpp/ggml-base.en.bin` | 140 MB |
| Parakeet TDT 0.6B v3 (accuracy alt, `--stt parakeet`) | `~/.cache/parakeet/ggml-model.bin` | 1.2 GB |
| Qwen 2.5 1.5B Instruct Q4_K_M (LLM, served warm) | `~/.cache/llama.cpp/qwen2.5-1.5b-instruct-q4_k_m.gguf` | 1.07 GB |

## Files

- `scripts/kavi.py` — main voice assistant (config from skill)
- `scripts/kavi-cli.sh` — `kavi` control CLI (start/stop/status/logs/correct/uncorrect/corrections)
- `scripts/kavi-trigger.sh` — xbindkeys hotkey trigger
- `scripts/start-whisper-server.sh` — persistent whisper-server (STT), start before Kavi
- `scripts/chat.sh` — legacy v0 (fixed 5s cuts, superseded)
- `scripts/venus.sh` — legacy wake-word prototype
- `config/corrections.json` — deterministic transcript correction dictionary (see below)
- `cache/` — temporary WAV files (gitignored)
- `~/.xbindkeysrc` — hotkey bindings

## Hotkey bindings

Print Screen or Right Ctrl → `kavi-trigger.sh` → flag file → Kavi cycle.

## Modes

- **Hotkey mode (default)**: Print Screen triggers one record-transcribe-dispatch cycle.
- `--always-on`: continuously listening (heavier on CPU, opt-in).
- `--once`: run one cycle and exit (for testing).
- `--tts`: enable Piper TTS reply in chat mode (default: text only, opt-in).
- `--stt parakeet`: use Parakeet instead of whisper base.en (more accurate, no persistent server, ~1.4s reload per cycle).

## Accuracy: corrections dictionary

Deterministic, zero-latency, zero-LLM word/phrase substitution applied to every
transcript right before dispatch (typing or chat). Reloaded from disk every
cycle, so no restart needed. `config/corrections.json`, `{"wrong phrase": "right phrase"}`.

```bash
kavi correct "sink up" "sync up"   # add/update an entry
kavi uncorrect "sink up"           # delete an entry
kavi corrections                   # list everything saved
```

An LLM-based cleanup pass (Qwen 2.5 1.5B rewriting the whole transcript) was
prototyped and rejected: ~1/3 hit rate on real mis-hearings, occasionally
silently dropped words with no way to detect it happened, and added 1.3-2.5s
latency per cycle. Not worth the risk vs. this deterministic approach.

## Mid-utterance verbal edit: "scratch that" / "delete that"

Say either phrase anywhere in a single dictation/chat utterance and everything
up to and including the last occurrence is discarded before dispatch - only
what follows gets typed/sent. Nothing after the last marker discards the
whole utterance (redo by pressing the hotkey again).

Because each cycle is one continuous recording -> one transcript -> one typed
block (see "Don't" below - no streaming partials), this discards back to the
*start of the current recording*, not just the last sentence. Practical
workaround (validated live): keep dictation bursts short - stop/restart the
hotkey every few seconds - so a "scratch that" only costs a small chunk.
Accepted as good V1 behavior; a future version could shrink the blast radius
(e.g. sentence-boundary-aware discard) but isn't planned yet.

## Startup (both servers, then Kavi)

Kavi is installed as a proper app (systemd `--user` services). Normal usage:

```bash
kavi start      # start all three services (or they're already autostarted at login)
kavi status     # check health
kavi logs       # follow the daemon log
kavi stop       # stop everything
```

First-time setup on a machine (or after `git pull`):
```bash
cd voice-chat && ./install.sh
```

Manual/dev startup (bypassing systemd, e.g. for quick local testing):
```bash
cd voice-chat/scripts
nohup ./start-whisper-server.sh > /tmp/whisper-server.log 2>&1 & disown
nohup ./start-llama-server.sh > /tmp/llama-server.log 2>&1 & disown
cd $HOME/learn/Code/voice-assistant/voice-chat
nohup python3 -u scripts/kavi.py > /tmp/kavi.log 2>&1 & disown
```

## Resource profile (typical cycle, measured)

| Component | CPU peak | VRAM | Duration |
|---|---|---|---|
| VAD recording | low | 0 | until 0.5s silence |
| Whisper base.en STT (warm, via HTTP) | ~1 core briefly | ~150 MB | ~200-400ms round trip |
| Parakeet STT (subprocess, `--stt parakeet`) | ~100% (1 core) | 1.3 GB | ~1.4-2 sec (model reload each cycle) |
| Qwen LLM (if chat, warm, streaming) | ~3 cores briefly | 0 (CPU only) | first token ~0.6s, full short reply ~1-2s |
| Piper TTS (if `--tts`) | low | 0 | 0.5-1 sec |
| xdotool type | low | 0 | <0.2 sec |

Total cycle (dictation only, whisper server warm): ~0.7-1 sec end-of-speech to text-at-cursor.
Total cycle (chat, warm, no TTS): ~1.5-2.5 sec.
Idle (waiting for hotkey, both servers warm): ~1.5-1.8 GB RAM, ~150-500 MB VRAM, ~0% CPU.

## Don't

- Don't try nerd-dictation. VOSK is broken on PipeWire, xdotool works.
- Don't add network calls. Voice chat is 100% local (servers are localhost-only).
- Don't run always-on mode without expecting fan noise on lighter hardware (per-cycle subprocess reload pegs a core continuously).
- Don't enable TTS by default. It adds latency and audio device contention. Opt-in via `--tts`.
- Don't try to build true streaming STT partials (mid-speech). Already tried and reverted (fan noise, and it's not actually how Wispr Flow behaves — it does fast finalization after silence, not live word-by-word). Focus on shortening the VAD tail and keeping STT warm instead.
- Don't try to warm Parakeet via whisper-server — whisper-server only serves whisper-family models, there's no server binary for Parakeet in this whisper.cpp build. If Parakeet needs to be warm, it requires a custom wrapper (not built, not currently worth the effort vs. whisper small.en).

## Skill

Intelligence lives in `config/kavi-config.md` (YAML frontmatter for tunable config). To change wake word, fuzzy threshold, VAD parameters, end-of-utterance silence: edit that file, restart Kavi.

## Known issues

- Parakeet has no persistent server; `--stt parakeet` still pays the ~1.4s reload cost per cycle. Whisper base.en (default) does not have this problem anymore.
- TTS uses Piper American English voice, doesn't match Indian English preference. Opt-in only via `--tts`.
- whisper-server, llama-server, and Kavi all autostart via systemd `--user` services (installed by `./install.sh`). Manual startup (see above) is only needed for dev/debug bypass of systemd.

## Roadmap

- **Voice isolation / noise-robust STT** (later, not started): improve accuracy in noisy/multi-speaker environments. Deferred until current single-user quiet-room accuracy work (corrections dictionary, edit commands) has been used enough to know if it's actually still needed.
