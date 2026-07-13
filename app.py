from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Literal

import librosa
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
MAX_AUDIO_SECONDS = 8 * 60
OUTPUT_DIR = Path("generated")
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="RD-8 AI Drummer v1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

Instrument = Literal[
    "kick",
    "snare",
    "closed_hat",
    "open_hat",
    "low_tom",
    "mid_tom",
    "high_tom",
    "clap",
    "rim",
    "cowbell",
    "cymbal",
]

# General MIDI percussion notes. Change these to match your RD-8 note map.
RD8_NOTE_MAP: dict[str, int] = {
    "kick": 36,
    "snare": 38,
    "closed_hat": 42,
    "open_hat": 46,
    "low_tom": 45,
    "mid_tom": 47,
    "high_tom": 50,
    "clap": 39,
    "rim": 37,
    "cowbell": 56,
    "cymbal": 49,
}


class SongSection(BaseModel):
    name: str
    start_bar: int = Field(ge=1)
    end_bar: int = Field(ge=1)
    energy: float = Field(ge=0, le=1)


class SongAnalysis(BaseModel):
    bpm: float = Field(gt=30, lt=300)
    duration_seconds: float = Field(gt=0)
    estimated_bars: int = Field(ge=1)
    time_signature: Literal["4/4"] = "4/4"
    beat_times_seconds: list[float]
    bar_energy: list[float]
    sections: list[SongSection]


class DrumHit(BaseModel):
    bar: int = Field(ge=1)
    step: int = Field(ge=0, le=15)
    instrument: Instrument
    velocity: int = Field(ge=1, le=127)
    microshift_ms: int = Field(default=0, ge=-40, le=40)


class DrumArrangement(BaseModel):
    title: str
    bpm: float = Field(gt=30, lt=300)
    bars: int = Field(ge=1, le=512)
    swing_percent: float = Field(default=50, ge=50, le=67)
    hits: list[DrumHit]


class GenerationResult(BaseModel):
    analysis: SongAnalysis
    arrangement: DrumArrangement
    midi_url: str
    arrangement_url: str


# ---------------------------------------------------------------------------
# Audio analysis
# ---------------------------------------------------------------------------

def normalize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return values
    low = float(np.min(values))
    high = float(np.max(values))
    if high - low < 1e-9:
        return np.zeros_like(values)
    return (values - low) / (high - low)


def make_sections(bar_energy: list[float]) -> list[SongSection]:
    """Simple v1 section segmentation based on sustained energy changes."""
    count = len(bar_energy)
    if count == 0:
        return [SongSection(name="song", start_bar=1, end_bar=1, energy=0.5)]

    # Prefer 8-bar phrases. Label them according to relative energy.
    sections: list[SongSection] = []
    for start_idx in range(0, count, 8):
        end_idx = min(start_idx + 8, count)
        energy = float(np.mean(bar_energy[start_idx:end_idx]))
        if start_idx == 0 and count >= 16:
            name = "intro"
        elif end_idx == count and count >= 16:
            name = "outro"
        elif energy >= 0.68:
            name = "high_energy"
        elif energy <= 0.32:
            name = "low_energy"
        else:
            name = "main"
        sections.append(
            SongSection(
                name=name,
                start_bar=start_idx + 1,
                end_bar=end_idx,
                energy=round(energy, 3),
            )
        )
    return sections


def analyze_audio(path: Path) -> SongAnalysis:
    y, sr = librosa.load(path, sr=22050, mono=True, duration=MAX_AUDIO_SECONDS)
    if y.size == 0:
        raise ValueError("The uploaded file contains no decodable audio.")

    duration = float(librosa.get_duration(y=y, sr=sr))

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo_raw, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_env,
        sr=sr,
        units="frames",
    )
    tempo = float(np.asarray(tempo_raw).reshape(-1)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).astype(float)

    if len(beat_times) < 4:
        raise ValueError("Could not detect enough beats in this recording.")

    # Fold common half/double-tempo errors into a practical drum tempo range.
    while tempo < 70:
        tempo *= 2
    while tempo > 180:
        tempo /= 2

    seconds_per_bar = 60.0 / tempo * 4.0
    estimated_bars = max(1, int(np.ceil(duration / seconds_per_bar)))

    rms = librosa.feature.rms(y=y)[0]
    rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr)

    bar_energy_raw: list[float] = []
    for bar_index in range(estimated_bars):
        start = bar_index * seconds_per_bar
        end = min((bar_index + 1) * seconds_per_bar, duration)
        mask = (rms_times >= start) & (rms_times < end)
        value = float(np.mean(rms[mask])) if np.any(mask) else 0.0
        bar_energy_raw.append(value)

    bar_energy = normalize(np.asarray(bar_energy_raw))
    bar_energy_list = [round(float(x), 3) for x in bar_energy]

    return SongAnalysis(
        bpm=round(tempo, 2),
        duration_seconds=round(duration, 3),
        estimated_bars=estimated_bars,
        beat_times_seconds=[round(float(x), 4) for x in beat_times],
        bar_energy=bar_energy_list,
        sections=make_sections(bar_energy_list),
    )


# ---------------------------------------------------------------------------
# LLM composition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are a drum arranger writing a new electronic drum-machine performance for a
Behringer RD-8. You receive deterministic song-analysis data, not the original
audio. Compose a tasteful accompaniment that follows the song's BPM, bar count,
section boundaries, and energy curve.

Rules:
- Return only data matching the supplied schema.
- Use a 16-step grid per 4/4 bar: step 0 is beat 1, 4 is beat 2, 8 is beat 3,
  and 12 is beat 4.
- The arrangement must fit the analyzed song rather than copy a copyrighted
  drum part note-for-note.
- Keep kick and snare musically coherent.
- Use closed hats for motion, open hats sparingly, and fills mainly near section
  boundaries.
- Avoid impossible duplicates of the same instrument at the same bar and step.
- Use velocity for accents and dynamics.
- Keep microshift subtle; most hits should be 0 ms.
- For a first version, favor a robust, playable pattern over excessive density.
"""


def arrangement_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "bpm": {"type": "number"},
            "bars": {"type": "integer"},
            "swing_percent": {"type": "number"},
            "hits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "bar": {"type": "integer"},
                        "step": {"type": "integer"},
                        "instrument": {
                            "type": "string",
                            "enum": list(RD8_NOTE_MAP.keys()),
                        },
                        "velocity": {"type": "integer"},
                        "microshift_ms": {"type": "integer"},
                    },
                    "required": [
                        "bar",
                        "step",
                        "instrument",
                        "velocity",
                        "microshift_ms",
                    ],
                },
            },
        },
        "required": ["title", "bpm", "bars", "swing_percent", "hits"],
    }


def compose_with_llm(
    analysis: SongAnalysis,
    style: str,
    creativity: str,
) -> DrumArrangement:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")

    client = OpenAI()
    user_prompt = f"""
Create an original RD-8 arrangement.

Requested style:
{style}

Creativity/density instruction:
{creativity}

Song analysis:
{analysis.model_dump_json(indent=2)}

Hard requirements:
- bpm must equal {analysis.bpm}
- bars must equal {analysis.estimated_bars}
- all hit bar values must be within 1..{analysis.estimated_bars}
- all step values must be within 0..15
"""

    response = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "rd8_drum_arrangement",
                "strict": True,
                "schema": arrangement_schema(),
            }
        },
    )

    raw = response.output_text
    try:
        arrangement = DrumArrangement.model_validate_json(raw)
    except ValidationError as exc:
        raise RuntimeError(f"Model returned invalid arrangement: {exc}") from exc

    arrangement.bpm = analysis.bpm
    arrangement.bars = analysis.estimated_bars

    # Deterministic cleanup.
    deduped: dict[tuple[int, int, str], DrumHit] = {}
    for hit in arrangement.hits:
        if hit.bar > arrangement.bars:
            continue
        key = (hit.bar, hit.step, hit.instrument)
        if key not in deduped or hit.velocity > deduped[key].velocity:
            deduped[key] = hit
    arrangement.hits = sorted(
        deduped.values(),
        key=lambda h: (h.bar, h.step, h.instrument),
    )
    return arrangement


# ---------------------------------------------------------------------------
# MIDI rendering
# ---------------------------------------------------------------------------

def arrangement_to_midi(arrangement: DrumArrangement, path: Path) -> None:
    ticks_per_beat = 480
    ticks_per_step = ticks_per_beat // 4
    channel = 9  # MIDI channel 10 in human numbering

    mid = MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    track = MidiTrack()
    mid.tracks.append(track)

    track.append(MetaMessage("track_name", name=arrangement.title, time=0))
    track.append(
        MetaMessage(
            "set_tempo",
            tempo=bpm2tempo(arrangement.bpm),
            time=0,
        )
    )
    track.append(
        MetaMessage(
            "time_signature",
            numerator=4,
            denominator=4,
            time=0,
        )
    )

    absolute_events: list[tuple[int, Message]] = []
    ms_per_tick = 60000.0 / arrangement.bpm / ticks_per_beat

    for hit in arrangement.hits:
        base_tick = ((hit.bar - 1) * 16 + hit.step) * ticks_per_step

        # Swing delays odd 16th notes within each eighth-note pair.
        swing_delay_ticks = 0
        if hit.step % 2 == 1 and arrangement.swing_percent > 50:
            eighth_ticks = ticks_per_step * 2
            swing_delay_ticks = int(
                eighth_ticks * ((arrangement.swing_percent / 100.0) - 0.5)
            )

        microshift_ticks = int(hit.microshift_ms / ms_per_tick)
        start_tick = max(0, base_tick + swing_delay_ticks + microshift_ticks)
        end_tick = start_tick + max(30, ticks_per_step // 3)

        note = RD8_NOTE_MAP[hit.instrument]
        absolute_events.append(
            (
                start_tick,
                Message(
                    "note_on",
                    channel=channel,
                    note=note,
                    velocity=hit.velocity,
                    time=0,
                ),
            )
        )
        absolute_events.append(
            (
                end_tick,
                Message(
                    "note_off",
                    channel=channel,
                    note=note,
                    velocity=0,
                    time=0,
                ),
            )
        )

    # note_off before note_on at identical ticks
    absolute_events.sort(
        key=lambda item: (
            item[0],
            0 if item[1].type == "note_off" else 1,
            item[1].note,
        )
    )

    last_tick = 0
    for absolute_tick, message in absolute_events:
        message.time = absolute_tick - last_tick
        track.append(message)
        last_tick = absolute_tick

    track.append(MetaMessage("end_of_track", time=0))
    mid.save(path)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse("index.html")


@app.get("/generated/{filename}")
def generated_file(filename: str):
    safe_name = Path(filename).name
    path = OUTPUT_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path)


@app.post("/api/generate", response_model=GenerationResult)
async def generate(
    audio: UploadFile = File(...),
    style: str = Form("Classic electro/techno; punchy but not overcrowded"),
    creativity: str = Form("Moderate density, clear 8-bar development, restrained fills"),
):
    suffix = Path(audio.filename or "song.wav").suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aiff", ".aif"}:
        raise HTTPException(status_code=400, detail="Unsupported audio format.")

    with tempfile.TemporaryDirectory() as tmp:
        temp_path = Path(tmp) / f"input{suffix}"
        with temp_path.open("wb") as out:
            shutil.copyfileobj(audio.file, out)

        try:
            analysis = analyze_audio(temp_path)
            arrangement = compose_with_llm(analysis, style, creativity)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    stem = Path(audio.filename or "song").stem
    safe_stem = "".join(c for c in stem if c.isalnum() or c in "-_")[:60] or "song"
    midi_name = f"{safe_stem}_rd8.mid"
    json_name = f"{safe_stem}_rd8.json"

    arrangement_to_midi(arrangement, OUTPUT_DIR / midi_name)
    (OUTPUT_DIR / json_name).write_text(
        arrangement.model_dump_json(indent=2),
        encoding="utf-8",
    )

    return GenerationResult(
        analysis=analysis,
        arrangement=arrangement,
        midi_url=f"/generated/{midi_name}",
        arrangement_url=f"/generated/{json_name}",
    )
