# RD-8 AI Drummer v1

This project:

1. uploads a WAV/MP3/etc.;
2. estimates BPM and beat locations with librosa;
3. computes one energy value per estimated bar;
4. asks an OpenAI text model to compose an original 16-step RD-8 arrangement;
5. validates the returned JSON;
6. writes a Standard MIDI File with Mido; and
7. lets Chrome play the JSON arrangement directly through Web MIDI.

## Prerequisites

- Python 3.11 or newer
- Google Chrome
- Your Mac connected to the RD-8 by USB MIDI or a USB-to-5-pin MIDI interface
- An OpenAI API key
- FFmpeg may be needed for some compressed audio formats. WAV should work without it.

## Install

```bash
cd rd8_ai_drummer_v1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="your-key-here"
```

The default model is `gpt-5.6-luna`. Override it with:

```bash
export OPENAI_MODEL="gpt-5.6-terra"
```

## Run

```bash
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Do not open `index.html` as a `file:///` URL. Serving it through localhost avoids browser
origin restrictions and is also the correct context for Web MIDI.

## RD-8 setup

1. Connect the RD-8 to the Mac.
2. Set the RD-8 to receive MIDI on channel 10, or edit `channel = 9` in `app.py`
   and the status bytes in `index.html`.
3. Verify the note map. The project currently uses General MIDI percussion notes.
   Change `RD8_NOTE_MAP` in `app.py` and `NOTE_MAP` in `index.html` to match the
   exact RD-8 mapping/configuration you use.
4. In Chrome, click **Connect MIDI**, then select the RD-8 MIDI output.

## Important v1 limitations

- This version estimates global tempo and assumes 4/4.
- Section detection is deliberately simple: eight-bar chunks labeled by energy.
- The LLM does not receive the copyrighted recording. It receives numerical analysis
  and composes a new accompaniment.
- It does not yet identify bass notes, chord changes, vocal phrases, or the exact
  existing drum part.
- Songs with rubato, changing meter, unusual tempo, or weak percussion may need
  manual BPM correction.

## JSON format

```json
{
  "title": "Example",
  "bpm": 128.0,
  "bars": 32,
  "swing_percent": 54,
  "hits": [
    {
      "bar": 1,
      "step": 0,
      "instrument": "kick",
      "velocity": 112,
      "microshift_ms": 0
    }
  ]
}
```

Each bar has 16 steps:

- 0 = beat 1
- 4 = beat 2
- 8 = beat 3
- 12 = beat 4
