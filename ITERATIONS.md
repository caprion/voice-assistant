# Design Journal — Voice Assistant Project

> Captures the full iteration history: what we tried, what failed, what worked, and the reasoning behind each pivot.
> Goal: future sessions (and human review via Copilot) can see not just the current state but the path that led there.
> Last updated: 2026-07-13

## Initial goals (start of project)

Two intertwined goals:

1. **voice-enforcer** — fine-tune a small local model to enforce Sumit's writing-hygiene rules (no em dashes, banned phrases removed, false humility cut). Ship as a CLI tool that takes a draft paragraph and returns a cleaned version.

2. **voice-chat (Kavi)** — build a local Wispr Flow analog. Hotkey activation, dictation at cursor, optional chat with local LLM, optional TTS reply. All inference on a 2015 Dell Inspiron 7559 (GTX 960M, 4 GB VRAM, 16 GB RAM).

The throughline: prove what modern AI work looks like on constrained hardware. The 2015 laptop can do real inference but hits real walls. The walls themselves are content.

## Hardware context (the constraint that shaped every decision)

- **Dell Inspiron 7559** (2015): i7-6700HQ, 4C/8T Skylake
- **GPU: GTX 960M, 4 GB VRAM**, Maxwell architecture, compute capability 5.0
- **RAM: 16 GB DDR4**
- **Disk: 859 GB free on /home**
- **OS: Linux Mint 22.3** with PipeWire 1.0.5 audio, X11 session
- **No CUDA Toolkit installed** initially. NVIDIA driver 580 with CUDA 13.0 support but no dev toolkit.

The 4 GB VRAM ceiling is the load-bearing constraint. Every iteration bumps into it.

## Iteration 1: Unsloth / Gemma 4 (FAILED — hardware incompatibility)

**Approach:** Use Unsloth, the standard fast fine-tuning framework. Train Gemma 4 (Google's newest small model).

**Why we tried this:** Unsloth is what most tutorials recommend for 2026. Gemma 4 is the latest "high accuracy" small model. Standard recipe.

**What happened:** Failed before we even started.

1. Unsloth installation page only lists RTX 30/40/50, Blackwell, DGX Spark. All SM 8.0+. Our SM 5.0 (Maxwell) isn't supported.
2. We tried Gemma 4 anyway. Unsloth's model page confirms it works with their framework. But the framework itself doesn't run on Maxwell.
3. bitsandbytes 0.42+ (the QLoRA library) drops Maxwell support entirely. The 4-bit kernels won't compile.

**Three dead ends, none of them hardware failures.** The hardware works. The software refuses to talk to it.

**Pivot:** If Unsloth won't run, what will? We needed a framework that:
- Supports Maxwell SM 5.0
- Does LoRA training (not just inference)
- Works without bitsandbytes

## Iteration 2: llama.cpp finetune (FAILED — POC only)

**Approach:** Use llama.cpp's built-in finetune tool. Same framework as inference. Should work since llama.cpp supports Maxwell.

**What we found:** llama.cpp finetune is a proof of concept.
- Only supports FP32 models
- No LoRA support
- README: "Finetuning of Stories 260K and LLaMA 3.2 1b seems to work with 24 GB of memory. For CPU training, compile llama.cpp without any additional backends such as CUDA. For CUDA training, use the maximum number of GPU layers."

**The math:** Qwen 2.5 1.5B in FP32 = 6 GB. Exceeds our 4 GB VRAM. Would need to drop to Qwen 0.5B (3 GB FP32) but smaller model + 3-variant training + honest evaluation = weeks of work for marginal value.

**Pivot:** If the framework we picked is in maintenance mode for Maxwell, we need to go up the stack. HF Transformers + PEFT was the obvious next step.

## Iteration 3: HF Transformers + PEFT (FAILED — VRAM wall)

**Approach:** Pin PyTorch 2.3.1 + CUDA 12.1 (Maxwell-compatible), transformers 4.44.2, peft 0.11.1. Plain fp16 LoRA on Qwen 2.5 1.5B. No bitsandbytes (incompatible), no Unsloth (incompatible). Just plain PyTorch + PEFT.

**What worked:** PyTorch loads on Maxwell, CUDA matmul passes, transformers can run Qwen 1.5B inference. The base model fits in 4 GB VRAM at fp16 (3 GB weights + 0.5 GB KV cache for short context).

**What broke:** Training.

Three failure modes hit in sequence:

1. **HF Trainer's GradScaler**: `Attempting to unscale FP16 gradients` error. The Trainer's automatic mixed precision uses a GradScaler that's incompatible with Maxwell's fp16 gradient path. Disabled scaler → no scaling → tiny gradients → no learning.

2. **OOM at the o_proj activation layer**: 3.5 GB model + 0.5 GB activations during forward = 4 GB exactly. Add gradients or backward = OOM. Even with max_len=512 and batch_size=1, the model is too big.

3. **Tried manual training loop, autocast(fp16) + LoRA in fp32**: OOM at the same layer. Skipping gradient checkpointing because Maxwell's implementation is flaky. Tried smaller context (256). Still OOM.

**The honest conclusion:** Qwen 2.5 1.5B physically doesn't fit for training on 4 GB VRAM. Drop to 0.5B and you get something that works, but loses ~30% capability on instruction following. The user has been clear: "smaller model would have really low accuracy" → don't force it.

**The pivot (Path C):** Ship the base model. The story becomes "inference works, training doesn't fit" — the wall is the content.

## Iteration 4: Path C — ship base model, write the wall

**Decision:** Abandon local fine-tuning. Use Qwen 2.5 1.5B Instruct as-is. The wall is the story.

**What we got:**
- 200 training pairs (still useful — could be applied to better hardware later)
- Eval scripts (llama.cpp + HF paths)
- Comparison report infrastructure
- Essay draft (1543 words, needs final pass for Path C framing)
- Demo script (revised for Path C)
- 5 skills capturing everything we learned

**Baseline numbers (base Qwen 2.5 1.5B, no fine-tuning):**
- em_dash recall: 60% (15/25)
- banned_phrase recall: 69%
- banned_adjective recall: 50%

These are the "model that ships without training" numbers. Decent, not great. The user can decide if 60% em dash recall is worth shipping.

**The lesson:** When hardware genuinely can't do what you want, don't force a worse version. Be honest about the limit, ship what does work, write the limit into the content.

## Voice chat subproject — iterations in parallel

While the voice-enforcer was hitting walls, we started building Kavi (voice-chat). This had its own iteration cycle.

### Iteration V0: chat.sh with fixed 5s recording (WORKED, but sluggish)

**Approach:** Bash script. pw-cat records for 5 seconds. parakeet-cli transcribes. llama-cli responds. Optional piper TTS.

**What worked:** End-to-end pipeline. Real transcription, real response, real TTS.

**What didn't:** 5-second fixed cuts felt unnatural. User had to time their speech. No wake word. No typing mode.

### Iteration V1a: Kavi with hotkey + VAD (WORKED)

**Approach:** Python harness (~280 lines now, was 400+). Skill-driven config (kavi-voice-assistant.md). xbindkeys + flag file for hotkey. webrtcvad for end-of-utterance. Smart dispatch (wake word → chat, otherwise → type at cursor).

**What worked:**
- Hotkey activation (Print Screen / Right Ctrl)
- VAD-based end-of-utterance (no more 5s cuts)
- Parakeet TDT 0.6B STT
- Qwen 2.5 1.5B LLM
- Piper TTS reply
- Fuzzy wake word matching (Levenshtein ≤ 2)
- Multi-token search ("Hey Kavi, ..." works)
- xdotool dictation mode (Wispr Flow primary use case)
- Audio gain warning

**What was tricky:**
- xdotool only works on X11. ydotool needed for Wayland.
- pkg_resources removed in setuptools 81+ broke webrtcvad. Pin setuptools<81.
- Fuzzy match needs to search multiple tokens, not just first word ("Hey Kavi" pattern).
- "Kavi" misheard as "Kabi" (v/b confusion in Indian English). Levenshtein distance handles it.

### Iteration V1b: Kavi always-on + streaming partials (FAILED — fan noise)

**Approach:** Remove hotkey, listen continuously. Use threading to do partial STT every 0.6s during speech. Show partials in the log as user speaks.

**What broke:** parakeet-cli at 100% CPU, continuously. Each partial transcription reloads the 1.2 GB model. Back-to-back calls = constant CPU load = fan noise. Plus the "streaming" wasn't visible — partials arrived 1-2s AFTER speech ended, not during.

**Diagnosis (via nvidia-smi + top):** parakeet-cli process at 102% CPU during a partial transcription. Model load is the bottleneck, not inference.

**The fix:** Drop streaming entirely. Keep hotkey mode as default. Make always-on opt-in via `--always-on` flag.

**The lesson:** True streaming STT needs persistent model (whisper-server) and a smaller model. With one-shot CLI invocations, "streaming" is fake. Better to be honest and ship a fast final-only path.

### Iteration V1c: Kavi optimized, hotkey default (CURRENT STATE)

**What we have now:**
- Hotkey mode is default (Print Screen / Right Ctrl)
- `--always-on` flag for users who want continuous
- 0.8s end-of-utterance silence (conversational feel)
- 8s silence bail (handles accidental hotkey presses)
- Fuzzy wake word match (multi-token, distance ≤ 2)
- Smart dispatch (chat vs dictation)
- 270 lines of pure plumbing, all intelligence in skill YAML frontmatter

**What's still slow:** Model reload on every cycle. Each Parakeet call = 1.5-2s. Each Qwen call = 3-5s. Total cycle = 5-9s.

**The fix (planned, not built):** whisper-server + llama-server. Persistent processes, models in memory. Cuts cycle time to 2-3s. Enables streaming LLM response (the real ChatGPT Live feel).

## Decisions log (for future reference)

| Decision | Date | Why | Alternative considered |
|---|---|---|---|
| Use Qwen 2.5 1.5B base | 2026-07-13 | Best small-model IF on constrained hardware. Apache 2.0. Multilingual. | Llama 3.2 1B (weaker IF), Llama 3.2 3B (doesn't fit VRAM), Gemma 4 (Unsloth-only) |
| Use Parakeet TDT 0.6B | 2026-07-13 | Best accuracy/speed for laptops. Built-in punctuation. | Whisper base.en (less accurate), Whisper large-v3 (too big), Distil-Whisper (slower) |
| Kavi as wake word | 2026-07-13 | 2 syllables, ends in vowel, hard k, Sanskrit origin | Coda (collides with Kodiak), Lyra (collides with liar), Vina (less known) |
| VAD aggressiveness 1 | 2026-07-13 | Sensitive enough for slow speakers | 0 (too sensitive to background), 2 (misses quiet speech), 3 (strict) |
| End-of-utterance 0.8s | 2026-07-13 | Fast conversational feel | 1.0s (slightly slow), 1.5s (too slow), 0.5s (false positives on brief pauses) |
| Fuzzy match ≤ 2 | 2026-07-13 | Handles "kabi"/"cavi"/"kavee" (Indian English phoneme confusions) | ≤ 1 (too strict), ≤ 3 (false positives like "coffee") |
| 5-token search depth | 2026-07-13 | Supports "Hey Kavi, ..." lead-in patterns | 1 (only first word), 3 (misses 2-word lead-ins) |
| Hotkey mode default | 2026-07-13 | Always-on causes fan noise, harder to disable | Always-on default (too eager) |
| Path C (no training) | 2026-07-13 | Honest about 4 GB VRAM wall. The wall is content. | Path A (force 0.5B training, lower quality) |
| Path B (smaller model via fp32 POC) | 2026-07-13 | Considered | Path C wins: less code, more honest |

## Lessons learned (for next project on this hardware)

1. **The wall is content.** When hardware genuinely can't do something, write that into the project story. Don't fake success with a worse version.

2. **Persistent models > per-call models.** For any non-trivial AI pipeline, get the models into long-lived processes. Per-call model loading is the #1 latency cost.

3. **Wake word needs fuzzy match from day 1.** Indian English speakers (and many others) hit phoneme confusions. Levenshtein distance ≤ 2 with multi-token search is the minimum viable.

4. **VAD sensitivity is per-user.** 0.8s end-silence works for one user. Build the skill config to make this tunable without code changes.

5. **Streaming is fake unless models are persistent.** "Streaming" with one-shot CLI invocations just queues up requests. Real streaming needs server processes.

6. **Always-on means always-on the CPU.** Hotkey mode is gentler on the laptop. Default to hotkey, opt-in to always-on.

7. **xbindkeys + flag file > signals.** Cleaner config, easier debugging, daemon can restart without breaking the hotkey.

8. **Fat skills thin harness.** All intelligence in markdown. Python reads config from skill. Future sessions pick up context. Improvements to skill benefit all uses.

9. **Git the brain, not just the code.** Skills and brain pages are the source of truth. Code is the implementation. Both should be versioned and discoverable.

## Open work (for next session and beyond)

### Priority 1: whisper-server + llama-server
- whisper-server for Parakeet TDT 0.6B (persistent)
- llama-server for Qwen 2.5 1.5B (persistent, streaming)
- HTTP-based calls from Kavi (httpx)
- Cuts cycle time from 5-9s to 2-3s
- Enables real streaming LLM response
- ~1-2 hours of work

### Priority 2: Streaming LLM response
- llama-server's `/v1/chat/completions` with `stream=True`
- Kavi prints tokens as they arrive
- TTS chunks by sentence
- The "ChatGPT Live" feel
- ~1 hour after servers are running

### Priority 3: Voice-enforcer essay final pass
- Update Training section to "Why training didn't fit"
- Add voice chat companion section
- Build interactive HTML explainer
- ~1-2 hours

### Priority 4: Demo recording with Flowblade
- Updated demo script already exists
- Record with SimpleScreenRecorder, edit in Flowblade
- ~1 hour

### Priority 5: Copilot review
- Share the repo (or design doc) with Copilot tomorrow
- Get feedback on architecture, missing edge cases, opportunities
- Iterate based on findings

## Things we'd do differently (with hindsight)

- **Start with whisper-server from the start.** Per-call model loading is so much slower. We wasted time building the per-call version first.

- **Skip Path B entirely.** When Path A's math doesn't work on paper (Qwen 1.5B fp16 = 3 GB + activations > 4 GB), don't run the experiment. Just go to Path C.

- **Test smaller model early.** Could have started with Qwen 0.5B to verify the training pipeline works on 4 GB VRAM, then attempt 1.5B. We went straight to 1.5B and OOMed.

- **Build the skill first.** Wrote the Python first, then the skill. Should have been the reverse. The skill is what future sessions need to understand the project.

- **Always-on is a feature, not a default.** It works, but it's a power-user feature. Defaulting to hotkey is the right call for most users.

- **Wake word search depth matters more than wake word choice.** "Kavi" vs "Lyra" vs "Coda" — the choice matters less than supporting "Hey Kavi, ..." patterns. Search depth was the bigger win.

## Files that capture this iteration

- `STATE.md` — current state, file map, open work
- `README.md` — project overview
- `brain/skills/kavi-voice-assistant.md` — Kavi architecture
- `brain/skills/voice-chat-cli-platform.md` — Linux Mint + PipeWire notes
- `brain/skills/local-stt-comparison-2026.md` — STT model choice
- `brain/skills/maxwell-cuda-constraints.md` — CUDA quirks
- `brain/skills/local-llm-finetune-2026.md` — Path A/B/C decision
- `brain/pages/postmortems/2026-07-12-oom-hang.md` — original OOM postmortem
- `voice-enforcer/explainer/essay-draft.md` — essay draft (1543 words, Path C)
- `voice-enforcer/explainer/demo-script.md` — demo script (Path C)

## Ready for Copilot review

The repo, STATE.md, and ITERATIONS.md should give a Copilot reviewer enough to evaluate:
- Architecture choices (Kavi design, model selection, VAD, fuzzy match)
- Path A/B/C decision (why training was abandoned)
- Open work (priority 1-5)
- Lessons learned

Areas where feedback would be valuable:
- Did we miss a model that's better suited to 4 GB VRAM?
- Is there a more efficient queueing/concurrency strategy?
- Are there better wake word options for Indian English specifically?
- Should we explore fine-tuning with a CPU offload approach we missed?
- Streaming architecture: is llama-server the right choice, or are there lighter alternatives?
