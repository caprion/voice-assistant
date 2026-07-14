#!/usr/bin/env bash
# chat.sh - Voice chat v0: record audio, transcribe with whisper.cpp, respond with llama.cpp
#
# Usage:
#     ./chat.sh                # record 5 seconds, then respond
#     ./chat.sh 8              # record 8 seconds
#     ./chat.sh --continuous   # loop until Ctrl+C (each cycle records 5s)
#
# Pipeline: pw-cat (PipeWire) -> whisper-cli -> llama-cli
# Zero network calls. Fully local.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WHISPER_BIN="${WHISPER_BIN:-$HOME/learn/whisper.cpp/build-cuda/bin/whisper-cli}"
WHISPER_MODEL="${WHISPER_MODEL:-$HOME/.cache/whisper.cpp/ggml-base.en.bin}"
PARAKEET_BIN="${PARAKEET_BIN:-$HOME/learn/whisper.cpp/build-cuda/bin/parakeet-cli}"
PARAKEET_MODEL="${PARAKEET_MODEL:-$HOME/.cache/parakeet/ggml-model.bin}"
LLAMA_BIN="${LLAMA_BIN:-$HOME/learn/llama.cpp/build-cuda/bin/llama-cli}"
LLAMA_MODEL="${LLAMA_MODEL:-$HOME/.cache/llama.cpp/qwen2.5-1.5b-instruct-q4_k_m.gguf}"
STT_ENGINE="${STT_ENGINE:-parakeet}"
CACHE_DIR="$PROJECT_DIR/cache"
DURATION="${1:-5}"
CONTINUOUS=false

if [[ "${1:-}" == "--continuous" ]]; then
    CONTINUOUS=true
    DURATION=5
fi

mkdir -p "$CACHE_DIR"

# --- Prerequisite checks ---
for bin in "$LLAMA_BIN"; do
    if [[ ! -x "$bin" ]]; then
        echo "Missing binary: $bin" >&2
        exit 1
    fi
done
case "$STT_ENGINE" in
    whisper)
        if [[ ! -x "$WHISPER_BIN" || ! -f "$WHISPER_MODEL" ]]; then
            echo "Whisper selected but binary/model missing." >&2
            exit 1
        fi
        ;;
    parakeet)
        if [[ ! -x "$PARAKEET_BIN" || ! -f "$PARAKEET_MODEL" ]]; then
            echo "Parakeet selected but binary/model missing." >&2
            exit 1
        fi
        ;;
    *)
        echo "Unknown STT_ENGINE: $STT_ENGINE (use 'whisper' or 'parakeet')" >&2
        exit 1
        ;;
esac
if [[ ! -f "$LLAMA_MODEL" ]]; then
    echo "Missing model: $LLAMA_MODEL" >&2
    exit 1
fi

# --- Detect audio source ---
record_audio() {
    local out="$1"
    local seconds="$2"
    if pw-cat --version >/dev/null 2>&1; then
        pw-cat --record --target 0 --format=s16 --channels=1 --rate=16000 \
            --seconds "$seconds" "$out" 2>/dev/null || \
        arecord -q -f S16_LE -r 16000 -c 1 -d "$seconds" "$out"
    else
        arecord -q -f S16_LE -r 16000 -c 1 -d "$seconds" "$out"
    fi
}

# --- Transcription ---
transcribe() {
    local wav="$1"
    case "$STT_ENGINE" in
        whisper)
            "$WHISPER_BIN" -m "$WHISPER_MODEL" -f "$wav" --no-timestamps --print-special 0 2>/dev/null \
                | tail -1 \
                | sed 's/^[[:space:]]*//'
            ;;
        parakeet)
            "$PARAKEET_BIN" -m "$PARAKEET_MODEL" -f "$wav" --no-prints 2>/dev/null \
                | grep -v "^\[" \
                | grep -v "^ggml_cuda_init" \
                | grep -v "^system_info" \
                | grep -v "^read_audio" \
                | grep -v "^main:" \
                | grep -v "^parakeet_" \
                | grep -v "^Successfully" \
                | grep -v "^$" \
                | head -1 \
                | sed 's/^▁/ /g'
            ;;
    esac
}

# --- Main loop ---
run_one_cycle() {
    local wav="$CACHE_DIR/cycle_$(date +%s%N).wav"
    local txt="$CACHE_DIR/cycle_$(date +%s%N).txt"

    echo "[$(date +%H:%M:%S)] Recording $DURATION seconds... (press Ctrl+C to abort)"
    if ! record_audio "$wav" "$DURATION"; then
        echo "Audio capture failed." >&2
        rm -f "$wav"
        return 1
    fi

    echo "[$(date +%H:%M:%S)] Transcribing via $STT_ENGINE..."
    local transcript
    transcript=$(transcribe "$wav")
    rm -f "$wav"

    if [[ -z "$transcript" || "$transcript" == "[BLANK_AUDIO]" || "$transcript" == "[inaudible]" ]]; then
        echo "[$(date +%H:%M:%S)] (no speech detected)"
        return 0
    fi

    echo "[$(date +%H:%M:%S)] You: $transcript"
    echo "[$(date +%H:%M:%S)] Qwen:"
    "$LLAMA_BIN" \
        -m "$LLAMA_MODEL" \
        -p "$transcript" \
        -n 256 \
        -c 2048 \
        --temp 0.7 \
        -ngl 999 2>/dev/null | tail -n +2
    echo ""

    # Cleanup transcript file
    rm -f "$txt"
}

if $CONTINUOUS; then
    echo "Continuous mode via $STT_ENGINE. Press Ctrl+C to exit."
    trap 'echo ""; echo "Exiting."; exit 0' INT TERM
    while true; do
        run_one_cycle || true
    done
else
    run_one_cycle
fi