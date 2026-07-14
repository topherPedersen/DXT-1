# RD-8 AI Drummer — OaF Drums edition

A complete standalone version of the RD-8 AI drum-transcription and Groove Mode
application. It uses:

- Demucs to isolate drums from a song.
- Magenta Onsets & Frames Drums, trained on E-GMD, to transcribe drums.
- A local deterministic Groove Mode engine to make stable repeating patterns.
- Web MIDI in Chrome or Edge to play the resulting MIDI through an RD-8.

No OpenAI API is used. Processing runs locally.

## Why Docker is used

OaF Drums is part of the archived Magenta TensorFlow codebase and depends on an
older software stack. The project isolates it in a Linux/AMD64 Docker container,
which avoids changing the Python installation on your Mac. Apple Silicon Macs
will run that container through Docker's x86 emulation.

## Requirements

1. Docker Desktop for Mac
2. Chrome or Microsoft Edge
3. An RD-8 connected by USB, or a USB MIDI interface connected to RD-8 MIDI IN

## Start

1. Unzip this project.
2. Open Docker Desktop.
3. Double-click `start.command`.

Or from Terminal:

```bash
cd rd8_oaf_drums_full
chmod +x start.command stop.command
./start.command
```

Open:

```text
http://127.0.0.1:8000
```

The first build and first startup are large because Docker installs Magenta,
TensorFlow, Demucs, and downloads the official E-GMD checkpoint.

## Stop

Press Control-C in the Terminal window, then run:

```bash
./stop.command
```

## Modes

### Full transcription

Returns the OaF drum transcription after mapping its drum pitches into the
RD-8-compatible General MIDI subset.

### Groove Mode

Finds a representative 1-, 2-, or 4-bar segment, simplifies it, repeats it for
a selected number of bars, and optionally adds phrase landmarks.

Recommended initial settings:

- 2-bar pattern
- 55% complexity
- 32 output bars
- phrase marker every 8 bars

## Architecture

```text
Browser
   |
FastAPI API container
   |
Demucs -> drums.wav
   |
OaF worker container
   |
Magenta OaF Drums -> MIDI
   |
RD-8 normalization
   |
Full transcription OR Groove Mode
   |
Web MIDI channel 10 -> RD-8
```

## Important limitations

- The Magenta repository was archived in January 2026.
- The OaF container uses an older TensorFlow ecosystem.
- This package has been syntax-checked and structurally validated, but the full
  model could not be executed in the artifact-building environment because the
  Docker images and large model dependencies must be downloaded on your Mac.
- The first Apple Silicon run may be slow because OaF uses an AMD64 container.
- Keep the ADTOF version installed separately until you have compared results.

## License note

This project includes a `THIRD_PARTY_NOTICES.md` file. The Magenta repository
code is Apache 2.0, and Demucs is MIT. The official E-GMD checkpoint is
downloaded separately from Google's Magenta storage at runtime. Before a
commercial release, independently confirm the terms covering redistribution
and commercial use of that checkpoint.


## Fix for an API image failure at `pip install -r requirements.txt`

This corrected release uses Python 3.10's full Debian image instead of the
minimal Python 3.11 slim image. It includes GCC, Git, pkg-config, libsndfile
development headers, and the other native build tools used by Demucs
dependencies.

When upgrading from the first OaF package, do not reuse the failed image. Run:

```bash
chmod +x rebuild.command
./rebuild.command
```

`rebuild.command` removes the previous containers, performs a clean image build,
and displays complete plain-text package installation logs.
