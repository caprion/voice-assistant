#!/usr/bin/env bash
# start-whisper-server.sh - persistent whisper.cpp server for Kavi's STT path.
# Eliminates the ~500ms per-cycle model-reload + CUDA-init cost of spawning
# whisper-cli fresh every hotkey press. kavi.py's transcribe() calls this over
# HTTP (POST /inference) with a subprocess fallback if this server is down.
#
# Only serves whisper-family models (base.en by default). Parakeet has no
# server counterpart in this whisper.cpp build - it stays on the per-cycle
# subprocess path (accuracy fallback, slower, see CLAUDE.md).
set -euo pipefail

BIN="${WHISPER_SERVER_BIN:-/home/nidhi/learn/whisper.cpp/build-cuda/bin/whisper-server}"
MODEL="${WHISPER_MODEL:-$HOME/.cache/whisper.cpp/ggml-base.en.bin}"
HOST="${WHISPER_SERVER_HOST:-127.0.0.1}"
PORT="${WHISPER_SERVER_PORT:-8090}"

if [[ ! -x "$BIN" ]]; then
    echo "Missing binary: $BIN" >&2
    exit 1
fi
if [[ ! -f "$MODEL" ]]; then
    echo "Missing model: $MODEL" >&2
    exit 1
fi

exec nice -n 5 "$BIN" -m "$MODEL" --host "$HOST" --port "$PORT" \
    --threads 3 --no-timestamps --beam-size 5
