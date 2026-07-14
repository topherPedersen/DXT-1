from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pipeline import PipelineOptions, process_audio

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
JOBS_DIR = Path(os.environ.get("JOBS_DIR", BASE_DIR / "data" / "jobs"))
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}
MAX_UPLOAD_BYTES = 250 * 1024 * 1024

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("rd8-oaf")

JOBS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="RD-8 AI Drummer — OaF", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/files", StaticFiles(directory=JOBS_DIR), name="files")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "demucs_available": shutil.which("demucs") is not None,
        "oaf_url": os.environ.get("OAF_URL", "http://oaf:8011"),
    }


async def save_upload(upload: UploadFile, destination: Path) -> None:
    total = 0
    with destination.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                destination.unlink(missing_ok=True)
                raise HTTPException(413, "Upload exceeds the 250 MB limit.")
            output.write(chunk)


@app.post("/api/process")
async def process(
    file: Annotated[UploadFile, File(...)],
    mode: Annotated[Literal["full", "groove"], Form()] = "groove",
    groove_bars: Annotated[int, Form()] = 2,
    groove_complexity: Annotated[float, Form()] = 0.55,
    output_bars: Annotated[int, Form()] = 32,
    phrase_markers: Annotated[bool, Form()] = True,
    phrase_every_bars: Annotated[int, Form()] = 8,
    demucs_model: Annotated[str, Form()] = "htdemucs",
) -> dict:
    filename = Path(file.filename or "upload.wav").name
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type. Use: {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
        )
    if groove_bars not in {1, 2, 4}:
        raise HTTPException(400, "Groove bars must be 1, 2, or 4.")
    if output_bars not in {8, 16, 32, 64, 128}:
        raise HTTPException(400, "Output bars must be 8, 16, 32, 64, or 128.")
    if phrase_every_bars not in {4, 8, 16}:
        raise HTTPException(400, "Phrase spacing must be 4, 8, or 16 bars.")
    if not 0 <= groove_complexity <= 1:
        raise HTTPException(400, "Complexity must be between 0 and 1.")

    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True)
    input_path = job_dir / f"source{extension}"

    try:
        await save_upload(file, input_path)
        result = process_audio(
            input_path,
            job_dir,
            PipelineOptions(
                mode=mode,
                groove_bars=groove_bars,
                groove_complexity=groove_complexity,
                output_bars=output_bars,
                phrase_markers=phrase_markers,
                phrase_every_bars=phrase_every_bars,
                demucs_model=demucs_model,
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        raise HTTPException(500, str(exc)) from exc
    finally:
        await file.close()

    midi_path = Path(result["midi_path"])
    return {
        "ok": True,
        "job_id": job_id,
        "mode": mode,
        "midi_url": f"/files/{job_id}/{midi_path.name}",
        "download_name": f"{Path(filename).stem}_{mode}_oaf_rd8.mid",
        "metadata": result["metadata"],
    }
