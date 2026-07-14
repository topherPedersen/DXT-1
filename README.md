# RD-8 Custom PyTorch Drum Transcriber — Prototype 1

This project replaces ADTOF and OaF with a small drum-transcription model that
you can train and own.

It does **not** use OpenAI or any paid API.

## What it predicts

The first model uses five product-oriented classes:

1. kick
2. snare
3. hi-hat
4. tom
5. cymbal

These are intentionally aligned with the simplified classes needed by the RD-8
and Groove Mode.

## Important limitation

This package contains the complete training and application code, but it does
not contain a trained model. You must train one before inference will work.

For the first experiment, use the Groove MIDI Dataset (GMD), which is much
smaller than E-GMD:

- GMD: about 13.6 hours / 4.76 GB
- E-GMD: about 444 hours / 90 GB

Start with GMD to prove that the architecture works. Move to E-GMD only after
the small experiment produces useful results.

## Dataset license

Google's Groove and Expanded Groove MIDI datasets are released for research and
reuse under Creative Commons attribution terms. Preserve the required
attribution and review the dataset page and license before commercial release.

## macOS setup

Python 3.10 or 3.11 is recommended.

```bash
cd rd8_custom_pytorch_transcriber
chmod +x install.command train.command run.command
./install.command
```

## Download the training data

Download `groove-v1.0.0.zip` from the official Magenta Groove MIDI Dataset page,
then extract it somewhere on your Mac.

The extracted folder must contain:

```text
info.csv
drummer1/
drummer2/
...
```

Each CSV row contains `audio_filename`, `midi_filename`, and `split`.

## Train

```bash
./train.command /absolute/path/to/groove-v1.0.0
```

The command creates:

```text
app/models/rd8_drum_transcriber.pt
```

Default training is deliberately modest:

- 12 epochs
- 8-second training segments
- batch size 8
- MPS on Apple Silicon when available
- CUDA when available
- otherwise CPU

Change those settings in `training/config.py`.

## Run the application

```bash
./run.command
```

Open Chrome or Edge at:

```text
http://127.0.0.1:8000
```

## Architecture

```text
Song
  |
Demucs
  |
isolated drums.wav
  |
Custom PyTorch CRNN
  |
five onset probability streams
  |
peak detection
  |
RD-8 MIDI
  |
Full Mode or Groove Mode
  |
Web MIDI channel 10
```

## Why this is commercially cleaner

- Application code: yours
- Model architecture and training code: yours
- Trained model weights: produced by you
- Training data: use only datasets with explicit commercial-compatible terms
- No ADTOF dependency
- No OaF checkpoint dependency
- No paid API

A product attorney should still review the final dataset, sample, and dependency
manifest before release.

## Recommended development sequence

1. Train on GMD.
2. Compare 20 songs against ADTOF.
3. Tune peak thresholds per class.
4. Add Demucs-style stem augmentation to training.
5. Train on E-GMD.
6. Add real commercial-song stems that you own or have permission to use.
7. Export the final model to ONNX or Core ML for easier distribution.


## Dataset path validation fix

This release rejects blank paths and directories before passing audio files to
TorchAudio. It also includes:

```bash
source .venv/bin/activate
python -m training.check_dataset /absolute/path/to/groove
```

Use that command to inspect malformed CSV rows or missing file references.


## Dependency versions used in this release

This package includes the user-tested `requirements.txt` versions:

```text
torch==2.13.0
torchaudio==2.11.0
torchcodec==0.14.0
scikit-learn==1.9.0
```

along with the remaining pinned dependencies in `requirements.txt`.
