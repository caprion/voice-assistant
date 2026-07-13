#!/usr/bin/env bash
# venus.sh - Voice assistant named Venus
#
# Activation model: prefix-style. Speak "Venus, <command>" to trigger.
# Stop: speak "Venus stop", "Venus bye", "Venus exit", or Ctrl+C.
# Optional TTS reply via piper.
#
# Usage:
#     ./scripts/venus.sh                  # 5s listening windows, whisper base.en
#     ./scripts/venus.sh --continuous     # continuous mode
#     ./scripts/venus.sh --no-tts         # text reply only, no spoken response
#     STT_ENGINE=parakeet ./scripts/venus.sh   # use Parakeet instead of whisper

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WHISPER_BIN="${WHISPER_BIN:-/home/nidhi/learn/whisper.cpp/build-cuda/bin/whisper-cli}"
WHISPER_MODEL="${WHISPER_MODEL:-$HOME/.cache/whisper.cpp/ggml-base.en.bin}"
PARAKEET_BIN="${PARAKEET_BIN:-/home/nidhi/learn/whisper.cpp/build-cuda/bin/parakeet-cli}"
PARAKEET_MODEL="${PARAKEET_MODEL:-$HOME/.cache/parakeet/ggml-model.bin}"
LLAMA_BIN="${LLAMA_BIN:-/home/nidhi/learn/llama.cpp/build-cuda/bin/llama-cli}"
LLAMA_MODEL="${LLAMA_MODEL:-$HOME/.cache/llama.cpp/qwen2.5-1.5b-instruct-q4_k_m.gguf}"
PIPER_VOICE="${PIPER_VOICE:-en_US-lessac-medium}"
PIPER_VOICE_DIR="${PIPER_VOICE_DIR:-/home/nidhi/learn/Code/voice-enforcer}"
STT_ENGINE="${STT_ENGINE:-parakeet}"
ENABLE_TTS=true
DURATION=5

for arg in "$@"; do
    case "$arg" in
        --continuous) DURATION=5 ;;
        --no-tts) ENABLE_TTS=false ;;
    esac
done

mkdir -p "$PROJECT_DIR/cache"

record_audio() {
    local out="$1" seconds="$2"
    if pw-cat --version >/dev/null 2>&1; then
        pw-cat --record --target 0 --format=s16 --channels=1 --rate=16000 \
            --seconds "$seconds" "$out" 2>/dev/null || \
        arecord -q -f S16_LE -r 16000 -c 1 -d "$seconds" "$out"
    else
        arecord -q -f S16_LE -r 16000 -c 1 -d "$seconds" "$out"
    fi
}

transcribe() {
    local wav="$1"
    case "$STT_ENGINE" in
        whisper)
            "$WHISPER_BIN" -m "$WHISPER_MODEL" -f "$wav" --no-timestamps --print-special 0 2>/dev/null \
                | tail -1 | sed 's/^[[:space:]]*//'
            ;;
        parakeet)
            "$PARAKEET_BIN" -m "$PARAKEET_MODEL" -f "$wav" --no-prints 2>/dev/null \
                | grep -v "^\[" | grep -v "^ggml_cuda_init" | grep -v "^system_info" \
                | grep -v "^read_audio" | grep -v "^main:" | grep -v "^parakeet_" \
                | grep -v "^Successfully" | grep -v "^$" | head -1 | sed 's/^▁/ /g'
            ;;
    esac
}

speak() {
    local text="$1"
    if ! $ENABLE_TTS; then return 0; fi
    local wav="$PROJECT_DIR/cache/venus_response.wav"
    source /home/nidhi/learn/Code/voice-enforcer/.venv/bin/activate 2>/dev/null || true
    python3 << PYEOF 2>/dev/null
import piper, wave
voice = piper.PiperVoice.load('${PIPER_VOICE_DIR}/${PIPER_VOICE}.onnx',
                               config_path='${PIPER_VOICE_DIR}/${PIPER_VOICE}.onnx.json')
with wave.open('${wav}', 'wb') as wf:
    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(voice.config.sample_rate)
    for chunk in voice.synthesize("""${text}"""):
        wf.writeframes(chunk.audio_int16_bytes)
PYEOF
    pw-play "$wav" 2>/dev/null
}

parse_venus() {
    # If transcript starts with "venus", strip prefix and return (matched, command)
    # Stop words: venus stop, venus bye, venus exit, venus quit, venus goodbye
    local transcript="$1"
    local cleaned
    cleaned=$(echo "$transcript" | sed -E 's/^[Vv]enus[,.\s]+//')
    if [[ "$cleaned" != "$transcript" ]]; then
        # Venus prefix detected
        local lower
        lower=$(echo "$cleaned" | tr '[:upper:]' '[:lower:]' | xargs)
        if [[ "$lower" =~ ^(stop|exit|quit|bye|goodbye|done|finish|that.?s.?all|that.?is.?all)$ ]]; then
            echo "__EXIT__"
            return
        fi
        echo "$cleaned"
        return
    fi
    echo ""
}

echo "=== Venus voice assistant ==="
echo "Engine: $STT_ENGINE  |  TTS: $ENABLE_TTS  |  Listen window: ${DURATION}s"
echo "Speak 'Venus, <command>' to ask. Say 'Venus stop' or press Ctrl+C to exit."
echo ""

running=true
trap 'echo ""; echo "Goodbye."; speak "Goodbye." || true; running=false' INT TERM

cycle=0
while $running; do
    cycle=$((cycle + 1))
    wav="$PROJECT_DIR/cache/venus_${cycle}_$(date +%s%N).wav"

    if $ENABLE_TTS; then
        echo -n "[$(date +%H:%M:%S)] Listening... "
    else
        echo "[$(date +%H:%M:%S)] Listening for ${DURATION}s..."
    fi

    if ! record_audio "$wav" "$DURATION"; then
        echo "Audio capture failed." >&2
        rm -f "$wav"
        continue
    fi

    transcript=$(transcribe "$wav")
    rm -f "$wav"

    if [[ -z "$transcript" ]]; then
        echo "(no speech)"
        continue
    fi

    echo "heard: $transcript"

    command=$(parse_venus "$transcript")
    if [[ -z "$command" ]]; then
        # No Venus prefix — silent, just keep listening
        echo "(no Venus prefix, ignoring)"
        continue
    fi

    if [[ "$command" == "__EXIT__" ]]; then
        echo "Venus signing off."
        speak "Goodbye." || true
        break
    fi

    echo "[$(date +%H:%M:%S)] Venus command: $command"
    echo -n "Venus: "
    response=$("$LLAMA_BIN" \
        -m "$LLAMA_MODEL" \
        -p "$command" \
        -n 256 \
        -c 2048 \
        --temp 0.7 \
        -ngl 999 2>/dev/null | tail -n +2)
    echo "$response"

    if $ENABLE_TTS; then
        speak "$response" || true
    fi
    echo ""
done

echo "Session ended after $cycle cycles."