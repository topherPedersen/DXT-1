from __future__ import annotations
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .midi_utils import events_to_midi, quantize_events
from .models import ExportRequest, QuantizeRequest
from .pipeline import PipelineError, process_audio

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
WORK = ROOT / "work"
WORK.mkdir(exist_ok=True)

app = FastAPI(title="RD-8 AI Drummer v2")

@app.get("/api/health")
def health():
    return {"ok": True}

@app.post("/api/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    skip_demucs: bool = Form(False),
    demucs_model: str = Form("htdemucs"),
    thresholds: str = Form(""),
    device: str = Form("cpu"),
):
    suffix = Path(file.filename or "audio.wav").suffix.lower()
    if suffix not in {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aiff", ".aif"}:
        raise HTTPException(400, "Unsupported audio type.")
    job_id = uuid.uuid4().hex
    job_dir = WORK / job_id
    job_dir.mkdir(parents=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename or f"upload{suffix}")
    source = job_dir / safe_name
    with source.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    try:
        drums_wav, raw_midi, events = process_audio(
            source, job_dir,
            skip_demucs=skip_demucs,
            demucs_model=demucs_model,
            thresholds=thresholds.strip() or None,
            device=device,
        )
    except PipelineError as exc:
        raise HTTPException(500, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Transcription failed: {exc!r}") from exc
    return {
        "job_id": job_id,
        "events": [e.model_dump() for e in events],
        "event_count": len(events),
        "drums_audio_url": f"/api/jobs/{job_id}/drums",
        "raw_midi_url": f"/api/jobs/{job_id}/raw-midi",
    }

@app.get("/api/jobs/{job_id}/drums")
def get_drums(job_id: str):
    job_dir = WORK / job_id
    candidates = list(job_dir.rglob("drums.wav"))
    if not candidates:
        # skip_demucs input can itself be WAV
        candidates = list(job_dir.glob("*.wav"))
    if not candidates:
        raise HTTPException(404, "Drum stem not found")
    return FileResponse(candidates[0], media_type="audio/wav", filename="drums.wav")

@app.get("/api/jobs/{job_id}/raw-midi")
def get_raw_midi(job_id: str):
    path = WORK / job_id / "adtof-raw.mid"
    if not path.exists():
        raise HTTPException(404, "MIDI not found")
    return FileResponse(path, media_type="audio/midi", filename="adtof-raw.mid")

@app.post("/api/quantize")
def quantize(request: QuantizeRequest):
    result = quantize_events(request.events, request.bpm, request.subdivision, request.strength)
    return {"events": [e.model_dump() for e in result]}

@app.post("/api/export")
def export_midi(request: ExportRequest):
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", request.filename)
    if not safe.lower().endswith((".mid", ".midi")):
        safe += ".mid"
    temp_dir = Path(tempfile.mkdtemp(prefix="rd8-export-"))
    path = temp_dir / safe
    events_to_midi(request.events, path, request.bpm, request.midi_channel)
    return FileResponse(path, media_type="audio/midi", filename=safe)

app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
