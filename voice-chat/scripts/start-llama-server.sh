#!/usr/bin/env bash
# start-llama-server.sh - persistent llama.cpp server for Kavi's LLM path.
# Runs Qwen 2.5 1.5B on CPU (not GPU) so the STT server keeps the GPU's
# limited VRAM to itself. CPU is fast enough here: ~15 tok/s, first token ~0.6s.
set -euo pipefail

BIN="${LLAMA_SERVER_BIN:-$HOME/learn/llama.cpp/build-cuda/bin/llama-server}"
MODEL="${LLAMA_MODEL:-$HOME/.cache/llama.cpp/qwen2.5-1.5b-instruct-q4_k_m.gguf}"
HOST="${LLAMA_SERVER_HOST:-127.0.0.1}"
PORT="${LLAMA_SERVER_PORT:-8081}"
THREADS="${LLAMA_SERVER_THREADS:-3}"
CTX="${LLAMA_SERVER_CTX:-2048}"

if [[ ! -x "$BIN" ]]; then
    echo "Missing binary: $BIN" >&2
    exit 1
fi
if [[ ! -f "$MODEL" ]]; then
    echo "Missing model: $MODEL" >&2
    exit 1
fi

exec nice -n 5 "$BIN" -m "$MODEL" --host "$HOST" --port "$PORT" \
    -ngl 0 --threads "$THREADS" --ctx-size "$CTX" --parallel 1
