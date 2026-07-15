# DXT-1: MP3 to Midi Drum Track Convertor

This version contains the complete backend, persistent conversion queue, and
browser download flow. No patching of an older codebase is required.

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

## macOS installation

Open Terminal, drag this folder into Terminal after typing `cd `, and press
Return. Then run:

```bash
chmod +x install_mac.sh run_mac.sh
./install_mac.sh
./run_mac.sh
```

Open:

```text
http://127.0.0.1:8000
```

The local launcher starts both the API and one conversion worker.

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

## Troubleshooting

### `ffmpeg` missing

Install Homebrew and run:

```bash
brew install ffmpeg
```

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
├── README.md
├── data/
│   ├── jobs.sqlite3
│   └── jobs/
└── static/
    └── index.html
```
