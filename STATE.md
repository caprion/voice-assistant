# Voice Assistant — Project State

> Captures where the project is, what works, what doesn't, and how to resume.
> Last updated: 2026-07-14

## What this is

A local voice assistant for Linux, inspired by Wispr Flow. Architecture: hotkey → record with Silero VAD (neural, ONNX) → transcribe with local STT (whisper small.en, beam-size 5) → smart dispatch → type at cursor or send to local LLM (Qwen 2.5 1.5B via llama-server) with streaming response.

All inference local on a 2015 Dell Inspiron 7559 (GTX 960M, 4 GB VRAM, 16 GB RAM, Linux Mint 22.3). No network calls during normal operation.

## Two subprojects

```
voice-assistant/
├── voice-enforcer/   Fine-tuning pipeline for a writing-style cleanup model (Path C — abandoned)
├── voice-chat/       Kavi — the working voice assistant (this is where the action is)
└── STATE.md          This file
```

## voice-enforcer/ — Path C (abandoned training)

**Goal:** fine-tune a 1-2B model on Sumit's published prose to enforce his writing-hygiene rules.

**What we did:**
- Built corpus: 9 published essays, ~10,700 words at `voice-enforcer/data/corpus/`
- Built rules canonical set at `voice-enforcer/data/rules.json`
- Generated 200 training pairs via MiniMax-M3 (Anthropic-compatible API) using `scripts/build_pairs.py`
- Built 3 training variants: `train_hf.py` (HF Trainer — broken on Maxwell), `train_manual.py` (manual loop — also broken on Maxwell), `train.sh` (3-run sweep wrapper)
- Built evaluation: `eval.py` (llama.cpp path), `eval_hf.py` (HF path), `compare.py` (side-by-side)
- Wrote essay draft: `voice-enforcer/explainer/essay-draft.md` (1543 words, Path C framing)
- Wrote demo script: `voice-enforcer/explainer/demo-script.md`

**Why we stopped:** the 4 GB VRAM ceiling on this hardware physically can't fit Qwen 2.5 1.5B training. We hit OOM at the o_proj activation layer. Dropping to 0.5B was possible but loses ~30% capability. Path C (ship the base model, write the wall into the essay) is the honest call.

**Baseline eval (base Qwen 2.5 1.5B, no fine-tuning):**
- em_dash: 60% recall
- banned_phrase: 69% recall
- banned_adjective: 50% recall

**What to do with it:** keep as a record. The training scripts + eval scripts + pair generation pipeline are usable on better hardware (8+ GB VRAM). The essay and demo script are publishable content (need final pass on Path C framing).

## voice-chat/ — Kavi (the working direction)

**Goal:** Wispr Flow analog. Hotkey activation, dictation at cursor, optional chat with local LLM, optional TTS reply.

**What we have (v0):**
- `kavi.py` — voice assistant harness, config loaded from skill
- `kavi-trigger.sh` — xbindkeys dictation/wake-word hotkey trigger (Right Ctrl / Pause)
- `kavi-chat-trigger.sh` — xbindkeys forced-chat hotkey trigger (Menu key)
- `kavi-indicator.py` — floating draggable state dot (idle/listening/processing)
- `~/.xbindkeysrc` — Right Ctrl / Pause (dictation) + Menu (chat) bindings
- `~/.cache/kavi/trigger`, `~/.cache/kavi/chat_trigger` — flag files (created on hotkey press)
- `~/.cache/kavi/state` — polled by the indicator dot
- 5 systemd `--user` services (autostart at login): `kavi.service`, `kavi-whisper-server.service`, `kavi-llama-server.service`, `kavi-xbindkeys.service`, `kavi-indicator.service`

**What's working:**
- Right Ctrl / Pause → dictation-or-wake-word cycle; Menu key → forced chat cycle (skips wake-word matching entirely)
- **Manual stop only**: press the same hotkey again to end recording — no auto-stop-on-silence, so pauses/thinking mid-sentence never cut you off (previously VAD-based end-of-utterance, removed 2026-07-14 per usability feedback)
- Silero VAD (neural, ONNX) gates against false "no speech" bails — dramatically more robust to this laptop's fan/ambient noise than webrtcvad (which flagged 64-99% of ambient noise as speech, replaced 2026-07-14)
- Whisper small.en STT via persistent whisper-server, beam-size 5 (free accuracy win, no latency cost measured)
- Qwen 2.5 1.5B LLM response (3-5s for short queries)
- Piper TTS reply (en_US-lessac-medium voice), opt-in via `--tts`
- Fuzzy wake word match (Levenshtein distance ≤ 1, tightened from ≤2 2026-07-14 — distance 2 caught common words like "have"/"gave"/"cave" as false positives)
- Multi-token search (finds "Kavi" anywhere in transcript, supports "Hey Kavi, ...")
- Smart dispatch: Menu-key press or wake word → chat (reply via notification only); otherwise → dictation at cursor via xdotool
- Audio gain warning if peak < 15% of max
- Bracketed/parenthesized STT noise tags (e.g. `[BLANK_AUDIO]`, `(machine whirring)`) filtered before typing

**What's not working / open issues:**
1. ~~Model reload every cycle~~ — **fixed 2026-07-14**: whisper-server (persistent, GPU, small.en) now serves STT via HTTP with subprocess fallback. Parakeet still per-cycle (no server support). llama-server (persistent, CPU) serves the LLM.
2. ~~No streaming LLM response~~ — **fixed**: llama-server's `/v1/chat/completions?stream=true`, Kavi prints tokens as they arrive via httpx.stream. First token ~0.6s.
3. **No streaming STT partials** — tried in Iteration V1b, reverted (fan noise from per-cycle model reload). Decided against retrying: this isn't actually how Wispr Flow behaves anyway (fast finalization after silence, not live word-by-word). Not on the roadmap.
4. **GPU contention** — resolved by design: Qwen stays on CPU (`-ngl 0`), whisper small.en on GPU (~300MB). No contention at this model size. Would need reassessment if upsizing to whisper medium.en (~1.5GB) or if warming Parakeet.
5. ~~No autostart~~ — **fixed 2026-07-14**: all 5 services run as systemd `--user` units, enabled at login via `install.sh`.
6. **Locale handling** — Qwen occasionally drops the "k" prefix from "Kavi" in TTS output. Cosmetic.
7. **Noise isolation in loud environments** — not yet implemented. Proposed: RNNoise or PipeWire's built-in noise-suppression module, applied before VAD/STT. Flagged as follow-up, not started.
7. **No idle detection** — servers stay warm always. Verified safe: ~1.5-1.8GB RAM, ~150-500MB VRAM steady-state, well within budget on 16GB/4GB hardware.

## File map (where things live)

```
/home/nidhi/learn/Code/voice-assistant/
├── voice-enforcer/
│   ├── data/
│   │   ├── corpus/           9 published essays, ~10.7K words
│   │   ├── pairs.jsonl       200 training pairs (generated)
│   │   ├── eval.jsonl        30 eval pairs (15% holdout)
│   │   └── rules.json         canonical rule set
│   ├── scripts/
│   │   ├── build_pairs.py    Gemini API → pairs (switched to Anthropic-compat)
│   │   ├── train_hf.py        HF Trainer (broken on Maxwell)
│   │   ├── train_manual.py    manual training loop (broken on Maxwell)
│   │   ├── train.sh           3-run sweep wrapper
│   │   ├── eval.py            eval via llama.cpp subprocess
│   │   ├── eval_hf.py         eval via HF Transformers
│   │   └── compare.py         side-by-side report
│   ├── explainer/
│   │   ├── essay-draft.md     1543 words, Path C framing
│   │   └── demo-script.md     revised for Path C
│   ├── README.md
│   ├── CLAUDE.md
│   └── .gitignore
├── voice-chat/
│   ├── kavi.py                voice assistant (~280 lines, config from skill)
│   ├── kavi-trigger.sh        xbindkeys trigger
│   ├── chat.sh                legacy v0 (fixed 5s cuts, superseded)
│   ├── venus.sh               legacy wake-word prototype
│   ├── README.md
│   ├── CLAUDE.md
│   └── .gitignore
└── STATE.md                   this file

/home/nidhi/learn/brain/skills/
├── kavi-voice-assistant.md    wake word, VAD, fuzzy match, mode dispatch
├── voice-chat-cli-platform.md  PipeWire, xbindkeys, xdotool on Linux Mint
├── local-stt-comparison-2026.md  whisper.cpp vs Parakeet TDT, when to use which
├── maxwell-cuda-constraints.md   CUDA build, PyTorch pinning, OOM on 4 GB
└── local-llm-finetune-2026.md    Path A/B/C decision tree, why training was abandoned
```

## Skills are the source of truth

The Python files are thin harnesses. All tunable intelligence lives in `brain/skills/`:
- Wake word choice, fuzzy threshold, search depth
- VAD aggressiveness, end-silence, bail timeout
- Frame size, sample rate
- Stop words set
- TTS voice
- Skill config is YAML frontmatter in the .md files

To tune Kavi: edit the skill, restart Kavi. No Python edits needed.

## How to resume work

```bash
# 1. Check what's running
ps aux | grep kavi.py
ps aux | grep -E "whisper-server|llama-server"

# 2. Start Kavi (hotkey mode, default)
cd /home/nidhi/learn/Code/voice-assistant/voice-chat
source ../voice-enforcer/.venv/bin/activate
nohup python3 -u scripts/kavi.py > /tmp/kavi.log 2>&1 &
disown

# 3. Verify xbindkeys is running
ps aux | grep xbindkeys

# 4. Check ~/.xbindkeysrc
cat ~/.xbindkeysrc

# 5. Trigger via Right Ctrl/Pause (dictation) or Menu key (chat)
# 6. Watch log
tail -f /tmp/kavi.log

# 7. Read relevant skill
cat /home/nidhi/learn/brain/skills/kavi-voice-assistant.md
```

## Open work — priority order for next session

1. ~~whisper-server for STT~~ — **done 2026-07-14**. Serving whisper small.en warm on GPU at 127.0.0.1:8090, beam-size 5. File: `voice-chat/scripts/start-whisper-server.sh`.

2. ~~llama-server for Qwen 2.5 1.5B~~ — **done**. Persistent, CPU-only, streaming enabled.

3. ~~Streaming LLM response~~ — **done**. httpx.stream against `/v1/chat/completions`, tokens print as they arrive.

4. ~~XDG autostart for Kavi daemon~~ — **done 2026-07-14, superseded the XDG-autostart plan**: all 5 components (kavi, whisper-server, llama-server, xbindkeys, indicator) run as systemd `--user` services instead, enabled via `install.sh`. More robust than `.desktop` autostart (restart-on-failure, proper logs via journalctl).

5. **GPU memory arbitration** — resolved for current model sizes (Qwen on CPU, whisper small.en on GPU, no contention). Revisit only if upsizing STT model further (e.g. medium.en).

6. **Finalize the essay** (Path C framing for AE publish)
   - "Why training didn't fit" section instead of "training results"
   - Voice chat companion section
   - Interactive HTML explainer at `voice-enforcer/explainer.html`
   - ~1-2 hours

7. **Record demo** with Kavi in flowblade
   - Updated demo script already at `voice-enforcer/explainer/demo-script.md`
   - ~30 min of recording + 30 min of editing

8. **Productize + multi-device** (new direction, 2026-07-14) — package Kavi as an installable app (systemd user services for the two servers + daemon, config file instead of hardcoded paths), and evaluate a client/server split so dictation triggers on any device while heavy inference optionally runs elsewhere (e.g. cf-openclaw for chat-only, latency-tolerant use). See `vm-sizing.md` for prior analysis of why cf-openclaw wasn't a good fit for the full latency-sensitive path.

## Auth

To push to caprion/voice-assistant on GitHub:
```bash
gh auth login    # run interactively, follow browser prompt
gh repo create caprion/voice-assistant --private --source=. --push
```

Once authed, all future pushes are: `git push caprion main`.

## Decisions made (for future reference)

- **Base model: Qwen 2.5 1.5B** (Apache 2.0, fits VRAM for inference, multilingual tokenizer)
- **STT model: whisper small.en (default, persistent server, beam-size 5)** — upgraded from base.en 2026-07-14 for better accuracy (2x slower per-cycle but negligible with beam search added at no extra cost measured). Parakeet TDT 0.6B available as accuracy alt via `--stt parakeet` but has no persistent server support, pays ~1.4s reload per cycle
- **TTS voice: piper en_US-lessac-medium** (American English, decent quality), opt-in via `--tts`
- **Wake word: "Kavi"** with fuzzy match (Levenshtein ≤ 1, tightened from ≤2 2026-07-14 — distance 2 false-matched common words like "have"/"gave"/"cave"/"wave"/"save")
- **VAD: Silero (neural, ONNX)** — replaced webrtcvad 2026-07-14. webrtcvad flagged 64-99% of this laptop's ambient fan noise as speech even at max aggressiveness; Silero measured 0% false positives on the same sample. Requires the official 512-sample-chunk + 64-sample-context-prepend calling convention (`SileroVAD` class in `kavi.py`) — feeding bare frames without the context buffer silently returns near-zero probability for all audio, a very easy mistake to make.
- **End-of-utterance: manual stop only** (2026-07-14) — auto-stop-on-silence removed entirely per usability feedback (any pause, even mid-thought, was cutting recordings short). Press the same hotkey again to end recording; `end_silence_sec`/`SILENCE_FRAMES` are now vestigial/unused.
- **8s silence bail** (handles accidental hotkey presses with no speech at all — the only remaining auto-stop path)
- **Training abandoned for Path C** (4 GB VRAM wall on Qwen 1.5B)
- **No streaming STT partials** (tried, reverted — fan noise; also not how Wispr Flow actually behaves, it does fast finalization not live word-by-word)
- **Hotkey activation default** (always-on is opt-in, not default)
- **Two separate hotkeys** (2026-07-14): Right Ctrl/Pause → dictation-or-wake-word; Menu key → forced chat (skips wake-word fuzzy-matching entirely, more reliable than relying on saying "Kavi" mid-sentence)
- **Floating state-dot indicator** (2026-07-14) — tkinter, draggable, position-persisted, polls `~/.cache/kavi/state`; gives instant visual feedback in lieu of true streaming STT partials
- **Persistent whisper-server + llama-server, always warm** (2026-07-14) — measured safe on 16GB/4GB hardware (~1.5-1.8GB RAM, ~150-500MB VRAM steady state), idle-unloading rejected because cold-start would break the "instant" feel
- **Kavi runs as systemd --user services** (2026-07-14) — 5 units total (kavi, whisper-server, llama-server, xbindkeys, indicator), autostart at login, restart-on-failure, no more manual nohup/disown; controlled via the `kavi` CLI (start/stop/restart/status/logs)
- **Desktop notifications for chat responses, gain warnings, STT server fallback** (2026-07-14) — reduces need to keep a terminal open watching logs; dictation mode intentionally has no notification since the typed text at cursor is itself the feedback

## Performance baseline

- Hotkey press → recording start: < 0.1s
- Recording end: manual (second hotkey press) — no fixed VAD-silence delay anymore
- STT (whisper small.en via persistent server, beam-size 5): ~2.1-2.4s for an 11s clip (beam search added no measurable latency over greedy)
- LLM (Qwen via persistent streaming server): first token ~0.6s, full short reply ~1-1.5s (was 3-5s with per-cycle subprocess)
- TTS (piper): 0.5-1s
- Total cycle (dictation, measured 2026-07-14): recording length (user-controlled) + ~2-2.5s transcribe-to-typed
- Total cycle (chat, streaming, no TTS): ~1.5-2.5s

## Productization (2026-07-14)

Kavi is now installed as a proper app on this laptop, not a set of scripts you manually nohup:

- **Config**: `voice-chat/config/kavi.env.example` is the git-tracked template. `~/.config/kavi/kavi.env` is the live per-machine copy (never overwritten by `install.sh` if it already exists) — this is what makes the app portable to a second machine: copy the repo, edit this one file's paths/ports, run `install.sh`.
- **Services**: `voice-chat/systemd/*.service` are git-tracked systemd `--user` unit templates, symlinked into `~/.config/systemd/user/` by `install.sh`. Three units: `kavi-whisper-server`, `kavi-llama-server`, `kavi` (the daemon, depends on the other two). All `Restart=on-failure`, all `WantedBy=default.target` (autostart at login).
- **CLI**: `voice-chat/scripts/kavi-cli.sh` is git-tracked, symlinked to `~/.local/bin/kavi`. Commands: `kavi start|stop|restart|status|logs [whisper|llama]`.
- **Install/reinstall**: `cd voice-chat && ./install.sh` — idempotent, safe to re-run after `git pull`.
- **Feedback without a terminal**: desktop notifications (`notify-send`) fire on chat responses, low mic gain, and STT-server-down fallback. Dictation mode deliberately has no notification — the typed text at the cursor is the feedback.

## Cross-device direction (design only, not built — 2026-07-14)

Sumit's stated north star: eventually trigger Kavi from other devices over Tailscale, this laptop stays the only inference host (it has the only GPU in the mix). The natural shape, when this is picked up:

- **This laptop remains the sole inference host.** Whisper-server and llama-server stay bound to `127.0.0.1` — do not expose them directly on the tailnet interface without adding authentication first. Raw `/inference` and `/v1/chat/completions` endpoints have no auth; anyone on the tailnet could hit them if bound to the Tailscale IP.
- **Other devices run a thin audio-relay client**, not their own STT/LLM: capture mic → stream/send audio over the tailnet to a small relay endpoint on this laptop → this laptop's Kavi does VAD/STT/dispatch/LLM as normal → result (text or spoken reply) relayed back to the originating device. This avoids needing GPU/CPU capacity on the other device and keeps one codebase for the actual intelligence.
- **cf-openclaw specifically**: per `vm-sizing.md`, it's CPU-only with no GPU, 2-5 tok/s for the LLM and slow STT — not a good *inference* host. Its plausible role in this design is as a *relay/reachability point* (already on the tailnet, always up) rather than doing any model inference itself, if the laptop is sometimes offline and something needs a queue/buffer. Not needed for the simple case of "phone or other laptop talks to my running laptop over Tailscale directly."
- **Trigger mechanism changes**: the current hotkey → flag-file → poll loop is inherently single-machine (X11, xbindkeys). A remote trigger needs a different entry point — e.g. a small authenticated HTTP endpoint on Kavi (`POST /trigger` with the audio attached, or a push-to-talk button in a companion app) rather than the flag file, since other devices can't write to this laptop's local filesystem or fire X11 hotkeys.
- **Security is the main unresolved question**: Tailscale itself provides network-level access control (only your tailnet devices can reach the laptop), but the services have zero application-level auth today. Before opening anything beyond `127.0.0.1`, add at minimum a shared-secret header check on any new endpoint.
- **Not started.** This is a planning note for when the "get this laptop right" phase is done. No networking changes have been made — all three services remain `127.0.0.1`-only right now.
