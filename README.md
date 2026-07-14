# RD-8 AI Drummer v2

Local MP3/audio → drum stem → drum MIDI → Behringer RD-8 pipeline.

## Pipeline

1. **Demucs / HTDemucs** extracts `drums.wav` from a mixed song.
2. **ADTOF-pytorch** detects five drum families: kick, snare, hi-hat, tom and cymbal.
3. The backend remaps General MIDI output to an RD-8-friendly map.
4. The browser lets you edit events, quantize, export MIDI, or play directly through Web MIDI.

## RD-8 note map used

| Voice | MIDI note |
|---|---:|
| Bass drum | 36 |
| Snare | 40 |
| Closed hi-hat | 42 |
| Open hi-hat | 46 |
| Low tom | 45 |
| Mid tom | 47 |
| High tom | 50 |
| Cymbal | 51 |

Confirm these against your RD-8's current global MIDI note-map settings. The app defaults to MIDI channel 10, but select the channel your RD-8 is configured to receive.

## macOS installation

Use Python **3.11** for the smoothest compatibility.

```bash
cd rd8-ai-drummer-v2
./setup-mac.sh
source .venv/bin/activate
./run.sh
```

Then open `http://127.0.0.1:8000` in Chrome.

Manual installation:

```bash
brew install python@3.11 ffmpeg
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The first transcription downloads the Demucs model. A full song is CPU-intensive; begin with a 20–30 second MP3 excerpt.

## Using the app

1. Upload an MP3, WAV, FLAC, M4A, OGG or AIFF file.
2. Leave **Input is already a drum-only stem** unchecked for a normal mixed song.
3. Start with **CPU**. Apple MPS may work for some PyTorch operations, but CPU is the conservative first test.
4. Click **Separate + transcribe**.
5. Inspect and edit the event table.
6. Connect the Mac to the RD-8 by USB, enable Web MIDI in Chrome, click **Connect MIDI**, and select the RD-8.
7. Verify the receive channel and click **Play**.
8. Export `rd8-drums.mid` after corrections.

## Threshold tuning

ADTOF accepts five comma-separated thresholds in this order:

```text
kick,snare,hi-hat,tom,cymbal
```

A documented example is:

```text
0.22,0.24,0.32,0.22,0.30
```

Lowering a threshold detects more hits but increases false positives. Raising it removes false hits but can miss quieter notes. Leave the field blank to use the model defaults first.

## Important limitations

- ADTOF predicts five broad families. It does not inherently distinguish open from closed hi-hat, individual tom pitches, rimshot, clap or cowbell. The first version maps its hi-hat class to closed hi-hat and its tom class to mid tom; edit those rows manually.
- Source separation can produce bleed and artifacts that become false drum hits.
- Quantization is optional. Use it for machine-tight patterns; avoid it when the recording deliberately swings.
- The app processes synchronously. Use short excerpts while testing.

## Troubleshooting

### `ffmpeg` not found

```bash
brew install ffmpeg
```

### ADTOF install cannot clone GitHub

Check internet access, then run:

```bash
pip install 'git+https://github.com/xavriley/ADTOF-pytorch.git@main'
```

### RD-8 appears but makes no sound

- Verify the RD-8 receive channel and the app's channel match.
- Confirm Chrome has MIDI permission.
- Verify the RD-8 USB device is selected, not an internal macOS synth.
- Check the RD-8 global MIDI note mapping.
- Try note 36 (bass drum) and note 40 (snare) in the event table.

### Too many or too few hits

Adjust one threshold at a time. Start with the documented example, then raise the noisy class by approximately `0.03`; lower a class that misses hits by approximately `0.03`.
