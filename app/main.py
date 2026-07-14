from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.pipeline import process

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"
JOBS = BASE / "data" / "jobs"
MODEL = BASE / "models" / "rd8_drum_transcriber.pt"
JOBS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="RD-8 Custom PyTorch Transcriber")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.mount("/files", StaticFiles(directory=JOBS), name="files")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/process")
async def api_process(file: UploadFile = File(...)):
    suffix = Path(file.filename or "song.wav").suffix.lower()
    job_id = uuid.uuid4().hex
    job_dir = JOBS / job_id
    job_dir.mkdir()
    source = job_dir / f"source{suffix}"

    try:
        with source.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                output.write(chunk)
        midi, metadata = process(source, job_dir, MODEL)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    finally:
        await file.close()

    return {
        "ok": True,
        "midi_url": f"/files/{job_id}/{midi.name}",
        "metadata": metadata,
    }
