from __future__ import annotations

import logging
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
JOBS_DIR = BASE_DIR / "data" / "jobs"
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}
MAX_UPLOAD_BYTES = 250 * 1024 * 1024

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("rd8-ai-drummer")

app = FastAPI(title="DXT-1: MP3 to Midi Drum Track Convertor", version="3.0.0")
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

    try:
        await save_upload(file, input_path)
        result = process_audio(
            input_path=input_path,
            job_dir=job_dir,
            options=PipelineOptions(
                mode=mode,
                groove_bars=groove_bars,
                groove_complexity=groove_complexity,
                output_bars=output_bars,
                phrase_markers=phrase_markers,
                phrase_every_bars=phrase_every_bars,
                demucs_model=demucs_model,
                device=device,
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Processing failed for job %s", job_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        await file.close()

    midi_filename = Path(result["midi_path"]).name
    return {
        "ok": True,
        "job_id": job_id,
        "mode": mode,
        "midi_url": f"/files/{job_id}/{midi_filename}",
        "download_name": f"{Path(original_name).stem}.mid",
        "metadata": result["metadata"],
    }
