# DXT-1: MP3 to Midi Drum Track Convertor

This page is intended for software developers interested in downloading,
building, modifying, or reading the source code for DXT-1. If you are not a 
software developer, and are just interested in using DXT-1 please visit the
[landing page](https://topherpedersen.github.com//DXT-1).

Or simply [Download DXT-1 Here](https://github.com/topherPedersen/DXT-1/releases/download/v1.0.0/DXT-1-1.0.0-arm64.dmg)

> **SOURCE-AVAILABLE SOFTWARE — NONCOMMERCIAL USE ONLY**
>
> DXT-1's original code is licensed under the
> [PolyForm Noncommercial License 1.0.0](LICENSE.md). Commercial use is not
> permitted under that license. DXT-1 is source-available, not OSI-approved
> open-source software. Third-party components remain under their own licenses;
> see [Third-Party Software and Assets](THIRD_PARTY_NOTICES.md).

This version contains the macOS Electron desktop app, complete backend,
persistent conversion queue, and MIDI download flow. Audio conversion runs on
the user's Mac instead of requiring a production server.

For the recommended local application, start with the
[DXT-1 macOS Desktop Guide](DESKTOP.md). The older browser/server deployment
remains available for people who specifically need it.

Planning a public deployment? Start with the
[DXT-1 Production Deployment Guide](DEPLOYMENT.md), including the automated
Ubuntu/DigitalOcean installer.

## Why DXT-1 is noncommercial source-available

DXT-1 depends heavily on ADTOF-PyTorch for automatic drum transcription.
ADTOF-PyTorch is a PyTorch port of the original ADTOF project and bundles
converted ADTOF model weights. The original ADTOF repository is licensed under
Creative Commons Attribution-NonCommercial-ShareAlike 4.0. Because Creative
Commons recommends software-specific licenses for software, DXT-1's original
code uses the software-focused PolyForm Noncommercial License instead of a
Creative Commons license.

The current ADTOF-PyTorch repository does not publish its own license. That is
an unresolved third-party licensing issue, not permission for unrestricted
use. Read [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) before distributing
or deploying DXT-1.

## Pipeline

1. Upload a song in the browser.
2. Demucs extracts the drum stem.
3. ADTOF-PyTorch transcribes the drum stem to MIDI.
4. Full mode returns that transcription.
5. Groove Mode identifies a representative 1-, 2-, or 4-bar section,
   simplifies it, repeats it, and optionally adds phrase landmarks.
6. The browser polls the queued job and offers the completed MIDI as a download.

## Concurrent conversion jobs

The web API and audio conversion worker run as separate processes. Each upload
is stored under a random UUID and recorded in `data/jobs.sqlite3`. The API
returns immediately, so long Demucs/ADTOF processing does not block other users
from uploading files or checking job status. The worker claims queued jobs
atomically and processes them in order.

One worker is the safe default because Demucs and ADTOF are memory- and
compute-intensive. More workers can be started when the server has enough CPU,
GPU, and RAM; SQLite prevents two workers from claiming the same job. Completed
and failed jobs are deleted after 24 hours by default.

## macOS desktop installation

Open Terminal, drag this folder into Terminal after typing `cd `, and press
Return. Then run:

```bash
chmod +x install_desktop_mac.sh run_desktop_mac.sh
./install_desktop_mac.sh
./run_desktop_mac.sh
```

The Electron window starts the private API and one conversion worker
automatically. See [DESKTOP.md](DESKTOP.md) for packaging, first-run setup,
signing, and distribution details.

## Production processes

Run the API and worker under a process supervisor as two separate services:

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000
python worker.py
```

Keep the `data` directory on persistent storage shared by the API and worker.
Do not run the API and worker on separate hosts unless that directory and its
SQLite database are on an appropriate shared filesystem. For multi-host or
high-volume deployment, replace SQLite/local files with a managed task queue
and object storage.

Production environment variables:

- `DXT_DATA_DIR`: persistent data directory; default `./data`
- `DXT_JOB_RETENTION_HOURS`: completed/failed file retention; default `24`
- `DXT_MAX_ACTIVE_JOBS`: queued/processing job limit; default `100`
- `DXT_WORKER_POLL_SECONDS`: queue polling interval; default `1`
- `DXT_STALE_JOB_HOURS`: age before an interrupted job is retried; default `6`

## Recommended Groove Mode settings

- Repeating pattern: 2 bars
- Complexity: 55%
- Generated length: 32 bars
- Phrase landmark: every 8 bars
- Demucs model: htdemucs
- Device: Automatic

## First-run behavior

Demucs may download model weights the first time it runs. ADTOF-PyTorch bundles
its model weights according to its project documentation.

## License

Original DXT-1 code and materials: [PolyForm Noncommercial 1.0.0](LICENSE.md).
Third-party software, model, font, and asset terms:
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Troubleshooting

### `ffmpeg` missing

Development from source requires FFmpeg. Install Homebrew and run:

```bash
brew install ffmpeg
```

Release DMGs bundle FFmpeg and do not require users to install it.

### MPS error on an Intel Mac

Select **CPU** in the web page. MPS is only for Apple Silicon-compatible
PyTorch installations.

### Processing returns an error

The worker records the error for the browser. Also inspect the worker logs.

## Project structure

```text
rd8_ai_drummer_v3_full/
├── app.py
├── pipeline.py
├── groove.py
├── job_store.py
├── worker.py
├── patch_adtof_compat.py
├── requirements.txt
├── install_mac.sh
├── run_mac.sh
├── install_desktop_mac.sh
├── run_desktop_mac.sh
├── electron/
├── package.json
├── DESKTOP.md
├── README.md
├── data/
│   ├── jobs.sqlite3
│   └── jobs/
└── static/
    └── index.html
```
