# RD-8 AI Drummer v3 — complete project

This version contains the complete backend and browser player. No patching of
an older codebase is required.

## Pipeline

1. Upload a song in the browser.
2. Demucs extracts the drum stem.
3. ADTOF-PyTorch transcribes the drum stem to MIDI.
4. Full mode returns that transcription.
5. Groove Mode identifies a representative 1-, 2-, or 4-bar section,
   simplifies it, repeats it, and optionally adds phrase landmarks.
6. The browser sends the notes to the RD-8 over Web MIDI channel 10.

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

Use Chrome or Edge for Web MIDI.

## RD-8 connection

Connect the Mac to the RD-8 using USB, or use a USB MIDI interface connected to
the RD-8 MIDI IN. In the page:

1. Click **Connect MIDI**.
2. Select the RD-8 or USB MIDI interface.
3. Generate or load the MIDI.
4. Click **Play**.

The app sends percussion notes on MIDI channel 10.

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

### MIDI output is missing

Use Chrome or Edge, click **Connect MIDI**, and confirm the RD-8 or interface is
visible to macOS in Audio MIDI Setup.

### Processing returns an error

The full backend error is returned to the page. Also inspect the Terminal
window where `run_mac.sh` is running.

## Project structure

```text
rd8_ai_drummer_v3_full/
├── app.py
├── pipeline.py
├── groove.py
├── requirements.txt
├── install_mac.sh
├── run_mac.sh
├── README.md
├── data/
│   └── jobs/
└── static/
    └── index.html
```
