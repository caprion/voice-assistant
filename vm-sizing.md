# cf-openclaw VM Sizing Analysis

> Can we host the voice assistant (Kavi backend) on cf-openclaw? Or do we need to upgrade?

## Current state: D2as_v4 (likely D2as_v5)

| Resource | Value |
|---|---|
| vCPU | 2 (shared cores) |
| RAM | 7.9 GB total, ~4 GB available |
| Disk | 32 GB free |
| GPU | none (CPU only) |
| OS | Ubuntu 24.04 |

## What Kavi backend needs

For llama-server hosting Qwen 2.5 1.5B (the LLM for chat mode):

| Resource | Qwen 1.5B Q4_K_M on CPU |
|---|---|
| File size | 1.07 GB |
| RAM at load | ~1.5-2 GB |
| RAM at inference | ~2-3 GB (model + KV cache + activations) |
| CPU speed (2 cores) | 2-5 tok/sec |
| Latency (50-token response) | 10-25 sec |

For whisper-server hosting Parakeet TDT 0.6B (the STT):

| Resource | Parakeet on CPU |
|---|---|
| File size | 1.2 GB |
| RAM at load | ~1.5-2 GB |
| Inference speed (2 cores) | 1-2x realtime (slow) |
| Not great on CPU | |

## Verdict on D2as_v5

- **LLM fits but slow:** 2.5 GB used of 4 GB available. 10-25 sec for short responses is borderline usable but not snappy.
- **STT slow on CPU:** Parakeet 0.6B without GPU is significantly slower than the laptop. whisper base.en would be faster but still slow.
- **Both running:** Total ~4 GB RAM. Crashes the VM if other workloads spike.
- **Other tasks:** cf-openclaw hosts the user's OpenClaw fleet, persistent sessions, routines. Voice assistant would compete.

**Recommendation: don't deploy on D2as_v5. Stay local on the laptop for inference.**

## SKU upgrade options (if you do want to deploy)

Pricing from Azure (2026, Linux, Pay-As-You-Go, East US):

| SKU | vCPU | RAM | Monthly | vs current |
|---|---|---|---|---|
| D2as_v5 (current) | 2 | 8 GB | ~$73 | baseline |
| D4as_v5 | 4 | 16 GB | ~$146 | 2x cost, comfortable for voice+STT |
| D8as_v5 | 8 | 32 GB | ~$293 | 4x cost, room for fleet + voice |

Source: [Azure VM pricing](https://azure.microsoft.com/en-us/pricing/details/virtual-machines/)

## VS Enterprise budget

- ~$150/mo Azure credits
- D4as_v5: at budget limit, single workload
- D8as_v5: over budget, room for fleet
- D2as_v5: comfortable, single workload

## My recommendation: stay on D2as_v5, host voice assistant on laptop

Reasons:
1. **Latency matters for dictation.** Laptop GPU: 19 tok/sec → 2-3 sec response. cf-openclaw CPU: 2-5 tok/sec → 10-25 sec response. Local is 5-10x faster.
2. **No GPU on cf-openclaw.** CPU-only is the wrong shape for LLM/STT.
3. **Other workloads on the VM matter more.** Fleet ops and persistent sessions have higher priority than voice chat.
4. **Streaming LLM response is now working locally.** Qwen 1.5B via llama-server on laptop, first token 0.6s. Already a win.

## Future: when to upgrade

If the user later wants:
- Multiple voice users → upgrade to D4
- Voice + fleet + everything else → upgrade to D8
- GPU acceleration → switch to NC-series (much more expensive, ~$500+/mo for NC T4)

For now: laptop is the right answer. The voice-enforcer essay captures this:
"Old hardware, new leverage. Inference fits where training doesn't, on a 2015 laptop."

## Deployment path if we do go to cf-openclaw later

1. Install llama.cpp (prebuilt binary or `apt install llama.cpp` on Ubuntu 24.04)
2. Pull Qwen 1.5B GGUF
3. Pull whisper base.en (smaller, faster on CPU)
4. Start both servers in background
5. Bind to Tailscale IP (not public)
6. Update Kavi to call `http://<tailscale-ip>:8081` instead of localhost
7. Document the deploy

Not urgent. The streaming LLM response works locally today.

## Streaming LLM response — local, working now

Already integrated into Kavi:
- llama-server running on laptop at 127.0.0.1:8081
- Kavi uses httpx.stream to call /v1/chat/completions
- First token: 0.6s, full response: 1.1s for "The capital of France is Paris."
- Mutex in Kavi prevents second hotkey press from firing concurrent cycle
- No thread pile-up (single-threaded, synchronous httpx.stream)

## horseflow reference

Looked at https://github.com/xdlawless2/horseflow. Similar project (push-to-talk dictation, Whisper + Ollama cleanup, server on port 8100). Validates our approach. Their stack:
- faster-whisper (vs our whisper.cpp)
- Ollama (vs our llama-server)
- Larger models (Whisper large-v3 + 8B/9B LLM)
- Requires 11 GB VRAM (we can't match this scale)

Different scale, similar pattern. No reason to switch to horseflow.
