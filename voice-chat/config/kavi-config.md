---
name: kavi-voice-assistant
config:
  wake_word: kavi
  fuzzy_max_distance: 1
  wake_word_search_tokens: 5
  vad_aggressiveness: 3
  end_silence_sec: 0.8
  bail_after_silence_sec: 8
  sample_rate: 16000
  frame_ms: 32
  max_utterance_sec: 30
  gain_warning_threshold_pct: 15
  partial_interval_sec: 0.6
  partial_min_speech_sec: 0.4
  wake_word_search_all: true
---

# Kavi tunable config

kavi.py reads the `config` block above (YAML frontmatter) at startup. Edit
a value here and restart Kavi, no code changes needed. This file is the
single source of truth for tunables; kavi.py itself is just plumbing.

## Why these defaults

**Wake word ("kavi")**: two syllables, ends in a vowel. One syllable words
miss too often ("vo" gets transcribed as "you", "no", "go"). Three syllables
are slower to say and easier to mangle. Avoid words with v/b or w/v
confusion, or "th" sounds, since STT models trip on those.

**Fuzzy match (`fuzzy_max_distance: 1`)**: exact string match fails on real
speech because STT mishears. Accept any token within Levenshtein distance 1
of the wake word (`kabi`, `cavi`, `kaavi` all match; `coffee` doesn't).
Raise to 2 if the wake word is missing valid hits; lower it if unrelated
words start triggering chat mode.

**VAD (`vad_aggressiveness: 3`, `end_silence_sec: 0.8`, `bail_after_silence_sec: 8`)**:
aggressiveness controls how strict speech detection is (0 most sensitive,
3 strictest). End-silence is how long a pause has to be before the utterance
is considered finished; shorter feels snappier but risks cutting off slow
speakers. Bail is the total-silence timeout that gives up on an accidental
hotkey press.

**Mode dispatch**: one default mode, not a manual toggle. If the transcript
contains the wake word (fuzzy-matched), it's routed to chat; otherwise it's
typed at the cursor as dictation. This mirrors how Wispr Flow behaves: you
don't switch modes, you just talk.

## Tuning tips

- Wake word missed often -> raise `fuzzy_max_distance` to 2.
- Utterances cut off mid-sentence -> raise `end_silence_sec` (try 1.0-1.5).
- Recordings hang too long on silence/misfires -> lower `bail_after_silence_sec`.
- Quiet mic/soft speaker -> lower `vad_aggressiveness` to 1 or 2.
