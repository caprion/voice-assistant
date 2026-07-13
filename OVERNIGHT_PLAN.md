# Overnight Plan — 2026-07-13

> What I'm doing in auto mode while Sumit sleeps. He'll review when he wakes up.

## The "whole vision" the user asked me to complete

Original goals (start of project):
1. **Fine-tune a small model on Sumit's writing** — apply writing-hygiene rules
2. **Build a local voice assistant** (Kavi)
3. **Run on a 2015 Dell Inspiron 7559**

Status at end of session:
- (1) Path C: abandoned training, ship base model only
- (2) Kavi v0: working, hotkey mode, smart dispatch
- (3) Hardware proven, walls documented

The user said: "fix the whole vision that we set otu also... plan and set everything up for that too over night."

Interpretation: don't just polish the essay. The voice-enforcer vision was real. Try once more, set up the missing pieces, document the journey.

## Tonight's work (5 tasks)

### Task 1: Refine essay using spine A approach
The current essay draft is at `voice-enforcer/explainer/essay-draft.md`. It's 1543 words, has 11 sections, tells a journey. Per the spine approach (from `brain/pages/decisions/spine-a-narrative-choice.md`), it should have:
- One clear thesis (falsifiable)
- First-person voice
- Code-first / B2C dev audience
- ~1800-2200 words
- No em dashes, no banned phrases

Action:
- Pick ONE thesis. Candidates:
  - "The wall is the content" — when hardware can't do something, write the wall into the story
  - "Old hardware, new leverage" — what 2015 can do with the right toolchain
  - "Inference fits where training doesn't, on a 2015 laptop"
- Restructure to spine A pattern (opening → fork → lever → companion → close)
- Apply voice rules rigorously
- ~2000 words

### Task 2: Try Qwen 0.5B training
We hit OOM on Qwen 1.5B at 4 GB VRAM. Qwen 0.5B fp16 = 1.5 GB. With activations, should fit.

This would actually deliver the voice-enforcer vision (a real fine-tuned model), not just Path C.

Action:
- Pull Qwen 0.5B Instruct GGUF for inference baseline
- Pull Qwen 0.5B Instruct safetensors for training
- Run `train_hf.py` or `train_manual.py` with Qwen 0.5B
- Eval on the same eval.jsonl
- If works: real LoRA adapter, integrate into Kavi
- If fails: extend Path C narrative

This is the highest-risk task. Run as background, log everything.

### Task 3: Set up video recording environment
The demo script is at `voice-enforcer/explainer/demo-script.md`. Recording environment needs to be ready when user wakes up.

Action:
- Install SimpleScreenRecorder (lightweight PipeWire-native screen capture)
- Install Flowblade (Linux-native video editor, optimized for older hardware)
- Verify both work (smoke test)
- Test microphone capture for narration
- Create a recording runbook the user can follow

### Task 4: Refine demo script
The current script was for the "training" narrative. If the essay is reframed (or if 0.5B training works), the script should match.

Action:
- After essay is final, sync the demo script to it
- Include both Path C AND 0.5B-attempt angles
- Keep TTS suggestions but note Piper American voice might not match Sumit's preference

### Task 5: Update docs and commit
- Update STATE.md with overnight progress
- Update ITERATIONS.md with the 0.5B attempt
- Commit everything to local git (push tomorrow with proper auth)

## Order of operations

1. **Plan doc** (this file) ← now
2. **Refine essay** with spine A
3. **Start Qwen 0.5B training** in background (will take 1-2 hours)
4. **Install video tools** (SimpleScreenRecorder, Flowblade)
5. **Refine demo script** to match essay
6. **Wait for training**, capture results
7. **Update STATE.md, ITERATIONS.md**
8. **Commit**

## Boundaries

What I will NOT do without explicit confirmation:
- Push to remote (no auth)
- Delete any existing files
- Modify the 5 skills in brain/
- Make API calls beyond what's already approved

What I will do (auto mode permission):
- Edit essays, scripts, docs in the voice-assistant repo
- Install needed tools (Flowblade, SimpleScreenRecorder)
- Run training in background
- Update STATE.md, ITERATIONS.md
- Commit to local git

## Success criteria

By morning:
- Essay is sharper (spine A applied, ONE thesis, ~2000 words, voice rules pass)
- Video tools are installed and verified
- Qwen 0.5B training has been attempted (success or honest failure documented)
- Demo script matches the essay
- STATE.md and ITERATIONS.md are current
- Local git has all overnight changes committed

User wakes up, reviews the changes, can push to caprion/voice-assistant with `gh auth login && git push`.
