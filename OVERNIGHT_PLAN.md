# Overnight Plan v2 — Streaming Kavi

> Revised after user feedback. Focus: perfect Wispr Flow streaming on this laptop.
> Path C is final (no training). Essay stays as-is. No video work tonight.

## The goal

Make Kavi work in true streaming mode without overwhelming the laptop:
- STT partials appear as user speaks (using whisper-server persistent process)
- LLM response streams token-by-token (using llama-server streaming HTTP endpoint)
- Resource use stays sane: don't peg CPU or GPU, no fan noise storm

## Architecture for v1

```
[Print Screen] → xbindkeys → ~/.cache/kavi/trigger (flag)
                                          ↓
[Kavi daemon] ← (polls flag every 100ms)
    ↓
[Audio capture with VAD] → 0.8s silence = end of utterance
    ↓
[POST /inference (audio.wav) → whisper-server] → partial transcript
    ↓ (poll every 0.4s for partials)
[Smart dispatch]
    ├─ wake word "Kavi" detected → [POST /v1/chat/completions?stream=true → llama-server]
    │                                  ↓ (SSE stream)
    │                              [print tokens as they arrive + TTS chunked]
    └─ no wake word → [xdotool type at cursor]
```

## Server config

| Server | Model | Backend | VRAM | RAM |
|---|---|---|---|---|
| whisper-server | Parakeet TDT 0.6B | GPU | ~1.5 GB | 0.3 GB |
| llama-server | Qwen 2.5 1.5B | CPU only | 0 | ~3 GB |

Total: 1.5 GB VRAM, 3.3 GB RAM. Plenty of headroom.

Why split GPU/CPU:
- Combined VRAM would be 4.5 GB (over the 4 GB ceiling)
- Qwen on CPU at 1.5B is slow (~2-4 tok/sec) but fine for short responses
- Parakeet on GPU is fast for streaming partials
- The split keeps total memory in budget

## Work plan (overnight)

### 1. Start whisper-server in background
- whisper.cpp build already has whisper-server binary
- Run with Parakeet model, listen on localhost:8080
- Verify with curl
- Log to /tmp/whisper-server.log

### 2. Start llama-server in background
- llama.cpp build already has llama-server binary
- Run with Qwen 1.5B Q4_K_M, CPU only (-ngl 0)
- Listen on localhost:8081
- Verify with curl
- Log to /tmp/llama-server.log

### 3. Refactor Kavi to use HTTP APIs
- Replace subprocess.run calls with httpx calls
- whisper-server: POST audio file → get JSON transcript
- llama-server: POST with stream=true → get SSE token stream
- Keep flag file + xbindkeys mechanism

### 4. Implement streaming LLM response
- httpx with stream=True
- Parse SSE chunks, print tokens to log as they arrive
- TTS chunk by sentence (Piper supports per-sentence synthesis)
- This is the "ChatGPT Live" feel

### 5. Implement streaming STT partials
- With persistent whisper-server, partials are fast (no model reload)
- Every 0.4s during speech, send current audio buffer to whisper-server
- Display partials in log
- Drop incomplete if a newer partial arrives

### 6. Resource monitoring
- Log GPU/CPU usage periodically
- If GPU pegged, throttle partial interval
- If CPU pegged, drop STT partials, only final

### 7. Test
- Hotkey → record → STT partials appear → final transcript
- "Kavi, what is X" → LLM streams tokens → spoken
- Verify CPU/GPU not pegged
- Document resource use

### 8. Update docs
- Note server config in STATE.md
- Update ITERATIONS.md with the streaming architecture
- Commit all overnight changes

## What I will NOT do

- Train any model (Path C is final)
- Rewrite the essay
- Install video tools
- Push to remote (no auth)

## Success criteria

By morning:
- whisper-server running on localhost:8080 with Parakeet
- llama-server running on localhost:8081 with Qwen (CPU)
- Kavi uses both via HTTP (no more subprocess model loads)
- LLM responses stream token by token
- STT partials appear during speech (faster cycle, persistent model)
- Resource use stays under 60% CPU and 50% GPU during normal operation
- STATE.md and ITERATIONS.md updated

User wakes up, presses Print Screen, sees streaming partials, gets ChatGPT Live feel from Kavi.
