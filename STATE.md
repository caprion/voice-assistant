# Voice Assistant — Project State

> Captures where the project is, what works, what doesn't, and how to resume.
> Last updated: 2026-07-13

## What this is

A local voice assistant for Linux, inspired by Wispr Flow. Architecture: hotkey → record with VAD → transcribe with local STT (whisper base.en or Parakeet TDT 0.6B) → smart dispatch → type at cursor or send to local LLM (Qwen 2.5 1.5B via llama-server) with streaming response.

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
- `kavi.py` — voice assistant harness, ~280 lines, config loaded from skill
- `kavi-trigger.sh` — xbindkeys hotkey trigger
- `~/.xbindkeysrc` — Print Screen / Right Ctrl bindings
- `~/.cache/kavi/trigger` — flag file (created on hotkey press)

**What's working:**
- Print Screen / Right Ctrl triggers recording via xbindkeys
- VAD-based end-of-utterance detection (0.8s silence threshold)
- Parakeet TDT 0.6B STT (1.5-2s per cycle, includes model load)
- Qwen 2.5 1.5B LLM response (3-5s for short queries)
- Piper TTS reply (en_US-lessac-medium voice)
- Fuzzy wake word match (Levenshtein distance ≤ 2)
- Multi-token search (finds "Kavi" anywhere in first 5 tokens, supports "Hey Kavi, ...")
- Smart dispatch: wake word → chat, otherwise → dictation at cursor via xdotool
- Audio gain warning if peak < 15% of max

**What's not working / open issues:**
1. **Model reload every cycle** — biggest cost. Each Parakeet call reloads 1.2 GB from disk (1-2s). Each Qwen call also pays startup cost. Fix: whisper-server + llama-server for persistent processes.
2. **No streaming LLM response** — the user wants ChatGPT Live feel. Fix: llama-server's streaming HTTP endpoint, Kavi prints tokens as they arrive, TTS chunks by sentence.
3. **No streaming STT partials** — we tried this but the Parakeet model load per partial was too expensive on this hardware. Real streaming would need a smaller model (whisper tiny) loaded persistently.
4. **GPU contention** — Parakeet (1.5 GB) + Qwen (3 GB) = 4.5 GB, exceeds 4 GB VRAM. Current workaround: serialize. Fix: put one on CPU.
5. **No autostart** — Kavi doesn't start at login. Add XDG autostart .desktop file.
6. **Locale handling** — Qwen occasionally drops the "k" prefix from "Kavi" in TTS output. Cosmetic.
7. **No idle detection** — Kavi holds models in memory always. Fix: release after N minutes idle, reload on demand.

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

# 5. Trigger via Print Screen or Right Ctrl
# 6. Watch log
tail -f /tmp/kavi.log

# 7. Read relevant skill
cat /home/nidhi/learn/brain/skills/kavi-voice-assistant.md
```

## Open work — priority order for next session

1. **whisper-server** for Parakeet TDT 0.6B
   - Persistent process, model stays in memory
   - Eliminates 1-2s per-cycle model load
   - ~30 min of work
   - File: `voice-chat/scripts/start-whisper-server.sh`

2. **llama-server** for Qwen 2.5 1.5B
   - Same idea — persistent process
   - Enables streaming output via HTTP
   - ~30 min
   - File: `voice-chat/scripts/start-llama-server.sh`

3. **Mutex + streaming LLM response** in kavi.py
   - Use httpx to call llama-server's `/v1/chat/completions` with `stream=True`
   - Print tokens as they arrive in the log
   - TTS chunk by sentence
   - ~1-2 hours

4. **XDG autostart** for Kavi daemon
   - `~/.config/autostart/kavi.desktop` launches at login
   - Optional: include whisper-server and llama-server startup
   - ~15 min

5. **GPU memory arbitration** between STT and LLM
   - Currently serialize. Better: STT on GPU, LLM on CPU when both needed
   - Or: smaller STT model (whisper tiny) to free VRAM for LLM
   - Defer until v1 servers are running

6. **Finalize the essay** (Path C framing for AE publish)
   - "Why training didn't fit" section instead of "training results"
   - Voice chat companion section
   - Interactive HTML explainer at `voice-enforcer/explainer.html`
   - ~1-2 hours

7. **Record demo** with Kavi in flowblade
   - Updated demo script already at `voice-enforcer/explainer/demo-script.md`
   - ~30 min of recording + 30 min of editing

## Auth

To push to caprion/voice-assistant on GitHub:
```bash
gh auth login    # run interactively, follow browser prompt
gh repo create caprion/voice-assistant --private --source=. --push
```

Once authed, all future pushes are: `git push caprion main`.

## Decisions made (for future reference)

- **Base model: Qwen 2.5 1.5B** (Apache 2.0, fits VRAM for inference, multilingual tokenizer)
- **STT model: Parakeet TDT 0.6B** (best accuracy/speed for laptops, built-in punctuation)
- **TTS voice: piper en_US-lessac-medium** (American English, decent quality)
- **Wake word: "Kavi"** with fuzzy match (Levenshtein ≤ 2, search first 5 tokens)
- **VAD: webrtcvad aggressiveness 1** (sensitive enough for slow speakers)
- **End-of-utterance: 0.8s silence** (conversational feel, fast response)
- **8s silence bail** (handles accidental hotkey presses)
- **Training abandoned for Path C** (4 GB VRAM wall on Qwen 1.5B)
- **No streaming STT partials** (model load too expensive for real-time on this hardware)
- **Hotkey activation default** (always-on is opt-in, not default)

## Performance baseline

- Hotkey press → recording start: < 0.1s
- Recording + VAD end: 0.8s after speech stops
- STT (Parakeet full cycle including model load): 1.5-2s
- LLM (Qwen full cycle including model load): 3-5s for short queries
- TTS (piper): 0.5-1s
- Total cycle (cold): 5-9s
- Total cycle (with persistent servers, future): 2-3s
