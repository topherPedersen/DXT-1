from __future__ import annotations

import logging
import os
import re
import importlib.util
import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI

from job_store import JobStore, QueueFullError

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = Path(os.getenv("DXT_DATA_DIR", BASE_DIR / "data")).expanduser().resolve()
JOBS_DIR = DATA_DIR / "jobs"
DATABASE_PATH = DATA_DIR / "jobs.sqlite3"
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}
MAX_UPLOAD_BYTES = 250 * 1024 * 1024
MAX_ACTIVE_JOBS = max(1, int(os.getenv("DXT_MAX_ACTIVE_JOBS", "100")))
JOB_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("dxt-api")

app = FastAPI(title="DXT-1: MP3 to Midi Drum Track Convertor", version="4.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
store = JobStore(DATABASE_PATH)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "demucs_available": importlib.util.find_spec("demucs") is not None,
    }


async def save_upload(upload: UploadFile, destination: Path) -> int:
    written = 0
    with destination.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                output.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail="The uploaded file exceeds the 250 MB limit.",
                )
            output.write(chunk)
    return written


def require_job(job_id: str) -> dict:
    if not JOB_ID_PATTERN.fullmatch(job_id):
        raise HTTPException(status_code=404, detail="Job not found.")
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


def public_job(job: dict) -> dict:
    response = {
        "ok": True,
        "job_id": job["id"],
        "status": job["status"],
        "mode": job["mode"],
        "download_name": job["download_name"],
    }
    if job["status"] == "queued":
        response["queue_position"] = store.queue_position(job["id"])
    elif job["status"] == "complete":
        response["download_url"] = f"/api/jobs/{job['id']}/download"
        response["metadata"] = job["metadata"]
    elif job["status"] == "failed":
        response["error"] = job["error"] or "Conversion failed."
    return response


@app.post("/api/process", status_code=status.HTTP_202_ACCEPTED)
async def process(
    file: Annotated[UploadFile, File(...)],
    mode: Annotated[Literal["full", "groove"], Form()] = "groove",
    groove_bars: Annotated[int, Form()] = 2,
    groove_complexity: Annotated[float, Form()] = 0.55,
    output_bars: Annotated[int, Form()] = 32,
    phrase_markers: Annotated[bool, Form()] = True,
    phrase_every_bars: Annotated[int, Form()] = 8,
    demucs_model: Annotated[str, Form()] = "htdemucs",
    device: Annotated[Literal["auto", "cpu", "cuda", "mps"], Form()] = "auto",
) -> dict:
    original_name = Path(file.filename or "upload.wav").name
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {extension or '(none)'}. "
            f"Use one of: {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
        )
    if groove_bars not in {1, 2, 4}:
        raise HTTPException(status_code=400, detail="Groove length must be 1, 2, or 4 bars.")
    if output_bars not in {8, 16, 32, 64, 128}:
        raise HTTPException(status_code=400, detail="Output bars must be 8, 16, 32, 64, or 128.")
    if phrase_every_bars not in {4, 8, 16}:
        raise HTTPException(status_code=400, detail="Phrase marker spacing must be 4, 8, or 16 bars.")
    if not 0 <= groove_complexity <= 1:
        raise HTTPException(status_code=400, detail="Complexity must be between 0 and 1.")

    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True)
    input_path = job_dir / f"source{extension}"
    options = {
        "mode": mode,
        "groove_bars": groove_bars,
        "groove_complexity": groove_complexity,
        "output_bars": output_bars,
        "phrase_markers": phrase_markers,
        "phrase_every_bars": phrase_every_bars,
        "demucs_model": demucs_model,
        "device": device,
    }

    try:
        await save_upload(file, input_path)
        store.enqueue(
            job_id=job_id,
            original_name=original_name,
            download_name=f"{Path(original_name).stem}.mid",
            mode=mode,
            options=options,
            max_active_jobs=MAX_ACTIVE_JOBS,
        )
    except QueueFullError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    finally:
        await file.close()

    logger.info("Queued job %s for %s", job_id, original_name)
    return {
        "ok": True,
        "job_id": job_id,
        "status": "queued",
        "status_url": f"/api/jobs/{job_id}",
    }


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    return public_job(require_job(job_id))


@app.get("/api/jobs/{job_id}/download")
def download(job_id: str) -> FileResponse:
    job = require_job(job_id)
    if job["status"] != "complete" or not job["midi_filename"]:
        raise HTTPException(status_code=409, detail="The MIDI file is not ready.")
    midi_path = JOBS_DIR / job_id / Path(job["midi_filename"]).name
    if not midi_path.is_file():
        logger.error("Completed job %s has no MIDI file", job_id)
        raise HTTPException(status_code=404, detail="The MIDI file is no longer available.")
    return FileResponse(
        midi_path,
        media_type="audio/midi",
        filename=job["download_name"],
    )
