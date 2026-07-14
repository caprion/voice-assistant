# Architecture — Voice Assistant

> System diagrams for the voice-assistant project. Mermaid renders in GitHub.

## High-level: hotkey → audio → text

```mermaid
flowchart LR
    User([User presses<br/>Right Ctrl]) --> Xbindkeys
    Xbindkeys[xbindkeys<br/>~/.xbindkeysrc] --> Trigger[trigger.sh<br/>creates flag file]
    Trigger --> Kavi[Kavi daemon<br/>polls every 100ms]
    Mic[Microphone] --> Kavi
    Kavi --> VAD{VAD<br/>speech detected?}
    VAD -->|Yes| Record[Record until<br/>0.8s silence]
    VAD -->|No 8s| Bail[Bail, no speech]
    Record --> STT[whisper.cpp<br/>Parakeet TDT 0.6B<br/>or base.en]
    STT --> Filter[Strip special tokens<br/>Filter noise]
    Filter --> Dispatch{Wake word<br/>detected?}
    Dispatch -->|Yes kavi| Chat[Stream to<br/>llama-server]
    Dispatch -->|No| Type[xdotool type<br/>at cursor]
    Chat --> Speaker[Response printed<br/>+ TTS if enabled]
    Speaker --> Output([User sees response])
    Type --> Output
```

## Process topology

```mermaid
flowchart TB
    subgraph User
        KB[Keyboard<br/>Right Ctrl]
        Mic[Microphone]
        Screen[Active window<br/>+ speakers]
    end

    subgraph Linux Mint
        XB[xbindkeys<br/>daemon]
        Kavi[Kavi<br/>Python daemon]
        Whisper[whisper-cli<br/>or parakeet-cli<br/>subprocess]
        Llama[llama-server<br/>persistent HTTP]
        Piper[piper TTS<br/>opt-in subprocess]
        Xdotool[xdotool<br/>type command]
    end

    KB --> XB
    XB -->|creates flag| Kavi
    Mic --> Kavi
    Kavi -->|spawns| Whisper
    Kavi -->|HTTP POST<br/>stream=true| Llama
    Kavi -->|spawns| Piper
    Kavi --> Xdotool
    Xdotool --> Screen
    Piper --> Screen
    Llama -.->|streams tokens| Kavi
```

## Hotkey chain (detailed)

```mermaid
sequenceDiagram
    participant User
    participant xbindkeys
    participant trigger.sh
    participant flag as ~/.cache/kavi/trigger
    participant Kavi
    participant whisper
    participant llama
    participant xdotool

    User->>xbindkeys: Right Ctrl (keydown + keyup)
    xbindkeys->>trigger.sh: bash /path/to/kavi-trigger.sh
    trigger.sh->>flag: touch
    Note over Kavi: polls every 100ms
    Kavi->>flag: TRIGGER.exists() → True
    Kavi->>flag: unlink (consumed)
    Kavi->>Kavi: mutex.busy = True
    Kavi->>Kavi: VAD record (webrtcvad)
    Kavi->>whisper: subprocess.run (parakeet-cli or whisper-cli)
    whisper-->>Kavi: transcript + special tokens
    Kavi->>Kavi: strip <|endoftext|>, filter noise
    alt wake word "kavi" in transcript
        Kavi->>llama: POST /v1/chat/completions?stream=true
        llama-->>Kavi: SSE chunks
        Kavi->>User: print tokens as they arrive
    else dictation mode
        Kavi->>xdotool: xdotool type --clearmodifiers
        xdotool->>User: text in active window
    end
    Kavi->>Kavi: mutex.busy = False
    Kavi->>Kavi: time.sleep(0.2) cooldown
```

## Smart dispatch decision tree

```mermaid
flowchart TD
    A[Transcript from STT] --> B[Strip special tokens]
    B --> C{Empty?}
    C -->|Yes| D[Return, no action]
    C -->|No| E{Parenthesized noise?}
    E -->|Yes: music/silence| F[Return, log as garbage]
    E -->|No| G[Tokenize, search wake word]
    G --> H{Fuzzy match<br/>distance ≤ 2<br/>in first 5 tokens<br/>or all}
    H -->|No| I[Dictation mode]
    H -->|Yes| J{Command is<br/>stop word?}
    J -->|Yes: stop/exit/bye| K[Exit Kavi]
    J -->|No| L[Chat mode]
    I --> M[xdotool type at cursor]
    L --> N[Stream to llama-server]
    N --> O[Print tokens as they arrive]
    O --> P[TTS if enabled]
```

## Streaming LLM response (chat mode)

```mermaid
sequenceDiagram
    participant Kavi
    participant llama as llama-server<br/>(persistent)
    participant Log as /tmp/kavi.log
    Kavi->>llama: POST /v1/chat/completions<br/>{stream: true, ...}
    llama-->>Kavi: SSE chunk 1 (delta "The")
    Kavi->>Log: print "The" (no newline)
    llama-->>Kavi: SSE chunk 2 (delta " capital")
    Kavi->>Log: print " capital"
    llama-->>Kavi: SSE chunk 3 (delta " of")
    Kavi->>Log: print " of"
    Note over Kavi,llama: ... until "Paris."
    llama-->>Kavi: data: [DONE]
    Kavi->>Log: print newline
    Note over Log: User sees tokens appear progressively
```

## Resource profile per cycle

```mermaid
gantt
    title One Kavi cycle (CPU STT, CPU LLM)
    dateFormat X
    axisFormat %s
    section Press
    VAD record (until silence) :a1, 0, 2000
    section STT
    whisper-cli load model :a2, after a1, 800
    whisper-cli inference :a3, after a2, 1500
    section Dispatch
    Wake word check :a4, after a3, 10
    xdotool type (dictation) :a5, after a4, 200
    section Cooldown
    Sleep 0.2s :a6, after a5, 200
    section OR (chat)
    llama-server first token (CPU) :b2, after a4, 600
    llama-server stream complete (50 tokens) :b3, after b2, 20000
```

## Skill-driven config (intelligence layer)

```mermaid
flowchart LR
    Skill[config/kavi-config.md<br/>YAML frontmatter]
    Skill -->|load at startup| Kavi
    Skill -.->|edit + restart| Config[Config values]
    Config --> Kavi
    Kavi --> Runtime[Runtime behavior]
```

Tunable via skill, no Python edit:
- `wake_word` (default: "kavi")
- `fuzzy_max_distance` (default: 2)
- `wake_word_search_tokens` (default: 5)
- `wake_word_search_all` (default: true)
- `vad_aggressiveness` (0-3, default: 1)
- `end_silence_sec` (default: 0.8)
- `bail_after_silence_sec` (default: 8)
- `sample_rate` (16000), `frame_ms` (30)
- `max_utterance_sec` (30)
- `gain_warning_threshold_pct` (15)

## Components and their data

| Component | Size | Where it lives | Notes |
|---|---|---|---|
| whisper base.en | 140 MB | `~/.cache/whisper.cpp/` | Fallback STT |
| Parakeet TDT 0.6B v3 | 1.2 GB | `~/.cache/parakeet/ggml-model.bin` | Default STT (more accurate) |
| Qwen 2.5 1.5B Instruct Q4_K_M | 1.07 GB | `~/.cache/llama.cpp/` | LLM for chat |
| Piper voice (en_US-lessac-medium) | ~60 MB | fetched separately, opt-in | TTS, opt-in |
| Remote VM | n/a | not deployed | Optional remote hosting, evaluated and rejected (see verdict below) |

## What's local vs what could be remote

| Component | Local (laptop) | Remote (small cloud VM) | Decision |
|---|---|---|---|
| Audio capture (pw-cat) | yes | no | Must be local (mic) |
| VAD (webrtcvad) | yes | no | Lightweight, must be local |
| STT (parakeet-cli / whisper-cli) | yes | yes | Local is faster. Remote option untested. |
| LLM (llama-server) | yes (now) | yes | Local works. Remote would be slow (CPU-only VM, no GPU). |
| TTS (piper) | yes | no | Audio output, must be local |
| xdotool | yes | no | Window injection, must be local |
| xbindkeys | yes | no | Keyboard input, must be local |

**Verdict:** Everything is local. The "remote" option is technically possible but not worth pursuing (a CPU-only 2-vCPU cloud VM is 5-10x slower than the laptop GPU for this workload).
