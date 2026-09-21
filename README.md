# Not3

Local-first AI note taking from audio. Drop in a recording, get back a
structured note with highlights — and run a pluggable library of **lenses**
over the transcript to surface psychological and communication patterns, each
tied to a verbatim quote and a timestamp.

Nothing leaves the machine. Transcription is whisper.cpp; the language work is
Ollama. Both run locally.

Windows and Apple Silicon are both first-class targets.

## Status

| Milestone | State |
|---|---|
| M0 — backend selection and benchmark | done |
| M1 — ingest + transcribe + storage | done |
| M2 — distill, highlight, anchoring, markdown export | done |
| M3 — lens engine + 3 starter lenses | done |
| M4 — Tauri + React desktop UI | done |
| M5 — speaker diarization | not started |
| M6 — packaging and installers | not started |
| M7 — cross-note insights and search | not started |

The desktop app runs the whole pipeline; the CLI still drives every stage
independently, which is what keeps prompt and lens work fast to iterate on.

```bash
cd app && npm install && npm run tauri dev
```

## Setup

Requires [uv](https://docs.astral.sh/uv/), [ffmpeg](https://ffmpeg.org/) and
[Ollama](https://ollama.com/) on PATH.

```bash
python scripts/fetch_whisper.py      # whisper.cpp binaries + large-v3-turbo (~1.9 GB)
cd engine && uv sync
uv run not3 doctor                   # confirms backends, models and tools
```

On Windows this pulls prebuilt CUDA and CPU builds. On macOS it builds
whisper.cpp from source so you get Metal — needs `cmake` and Xcode command
line tools.

## Use

Open the app, drop in a recording, and it transcribes, summarizes, highlights
and runs the lenses — streaming progress as it goes. Every quote in the app,
anywhere, plays the audio it came from.

The same pipeline from a terminal:

```bash
uv run not3 transcribe recording.m4a   # any audio or video ffmpeg can open
uv run not3 process 1                  # summary, key points, action items, highlights
uv run not3 lens 1 -v                  # pattern lenses, with each finding printed
uv run not3 notes                      # what's in the library
uv run not3 show 1                     # the transcript
```

Notes are exported as markdown with YAML frontmatter, Obsidian-compatible, to
`%LOCALAPPDATA%\Not3\export` (`~/Library/Application Support/Not3/export` on
macOS).

For working on prompts and lenses without waiting on audio:

```bash
uv run not3 import-transcript tests/fixtures/session.txt
```

## Measured on this machine

RTX 5070 Laptop (sm_120 Blackwell), `large-v3-turbo`, 308 s of audio:

| backend | time | realtime factor | 60 min recording |
|---|---|---|---|
| CPU | 201.4 s | 0.654× | ~39 min |
| CUDA | 8.9 s | 0.029× | ~1.7 min |

## How it works

```
audio ──▶ ffmpeg 16 kHz mono ──▶ whisper.cpp ──▶ segments + word timings
                                                        │
                                   ┌────────────────────┤
                                   ▼                    ▼
                            Ollama: distill      Ollama: lenses
                                   │                    │
                                   └──── anchoring ─────┘
                                            │
                                   SQLite + markdown export
```

### The shell and the engine

The Tauri shell starts the Python engine as a child process and talks to it
over HTTP on 127.0.0.1. Three details are load-bearing:

- **The engine picks its own port** (binds 0) and reports it on stdout. Having
  the shell pre-bind a socket and close it is a race.
- **The token is passed by environment variable**, never argv — argv is
  readable by any local process on Windows via WMI.
- **A Job Object with `KILL_ON_JOB_CLOSE`** guarantees the engine dies with the
  app. Tauri does not reliably reap child processes (tauri#5611), so without
  this a force-quit leaves Python holding the GPU and the database. Verified by
  force-killing the app and confirming all three child processes died.

Audio is served with HTTP range support, unauthenticated: a bearer token
cannot be attached to an `<audio src>`, and putting it in the query string
would leak it into logs. Without ranges the player cannot seek at all.

### Anchoring

The central safety property. A JSON schema makes a model's output
well-shaped; it says nothing about whether the quote inside it is real. Every
highlight and every finding must carry a `segment_id` and a verbatim `quote`,
and before anything is stored:

- the segment must exist in the chunk the model was shown,
- the quote must fuzzy-match that segment's text (punctuation and case
  ignored — models re-punctuate while reproducing words exactly),
- confidence must clear the lens threshold.

Matching is against the **whole chunk**, not a single segment. ASR segment
boundaries fall wherever the decoder happened to stop — often mid-clause, and
on a real recording the median segment is a fragment — so a quote worth
reporting usually spans two or three of them. Requiring a quote to fit inside
one segment threw away genuine verbatim evidence at about a 70% rate on real
audio; a hand-written fixture with one sentence per segment hid it completely.
A quote is attributed to the segment it starts in, and its end time comes from
the segment it ends in, so clicking it plays the whole quote.

Real speech attributed to the wrong line is **relocated** and counted, not
discarded. Text that appears nowhere in what the model was shown is
**dropped** and counted. Drop rates are stored per lens per model in
`lens_runs`, because that number is how you tell a sharp lens from a sloppy
one and how you compare two models on your own material.

What gets stored is the **transcript's own text** for the matched span, not
the model's retyping of it. Models quietly tidy disfluencies — on a real
recording the transcript said "I don't know I I don't really" and the model
returned it with the stutter removed, scoring 97 and passing the threshold.
Taking the words from the transcript makes "verbatim" true by construction
rather than true to within a threshold.

A consequence worth stating plainly: nothing in this app can claim something
was said unless it was said, in the words it was said in.

### Context sizing

Ollama defaults `num_ctx` to **4096 regardless of what the model supports** —
qwen3.5:9b handles 262144. A prompt near that limit leaves no room to answer,
and the reply arrives as valid-looking JSON cut off mid-token, reported as a
schema violation. The engine therefore sizes the window per request from the
actual prompt plus expected output, and a reply that still runs out of room is
retried with a larger one before failing. `max_num_ctx` in settings is the
ceiling it may ask for; lower it if the KV cache pushes the model out of VRAM.

### Lenses

A lens is a YAML file: categories, each with a definition, an example that
counts, and a near-miss that does not. Drop one into
`%LOCALAPPDATA%\Not3\lenses` and it appears — no code, no rebuild. Reusing a
built-in `id` replaces that built-in, so the shipped lenses can be edited
without being lost on upgrade.

Three ship by default: **cognitive distortions**, **emotional arc** and
**communication patterns**.

Two design details that turned out to matter more than expected, both found by
running the lenses against a fixture with known answers:

- **Near-miss examples carry the precision.** Without a `negative_example`,
  a lens fires on anything tonally adjacent to its subject.
- **Rejection needs a channel.** Every finding carries a `verdict` of
  `instance` or `near_miss`, and only `instance` is stored. Without it, a
  model asked to consider and reject a line will return it anyway — with a
  rationale explaining why it does not qualify. Silence is not a usable way
  to express "I checked this and ruled it out", so the schema provides one.

### On the psychological features

These are observations about language, anchored to quotes, with a confidence
and a rationale attached. They are not a clinical or diagnostic assessment,
the built-in lenses use descriptive rather than diagnostic vocabulary, and the
disclaimer travels with the data into the markdown export rather than living
only in the UI.

## Layout

```
engine/not3/
  config.py        platform paths, backend discovery
  db.py            SQLite access
  schema.sql       every finding FK's to a real segment
  cli.py           the whole pipeline, no UI required
  llm/
    ollama.py      structured output + embeddings
    chunker.py     windowing, carrying segment ids into the prompt
    anchor.py      the anchoring gate
  pipeline/
    ingest.py  asr.py  distill.py  highlight.py  lens.py  export.py
  lenses/*.yaml    the three starter lenses
scripts/
  fetch_whisper.py   binaries + models for this platform
  bench_asr.sh       measure every installed backend
tests/               anchoring, chunking and lens-loading
```

## Tests

```bash
cd engine && uv run pytest ../tests -q
```
