from __future__ import annotations

import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

CHECKPOINT_URL = (
    "https://storage.googleapis.com/magentadata/models/"
    "onsets_frames_transcription/e-gmd_checkpoint.zip"
)


def ensure_checkpoint(model_dir: Path) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_markers = list(model_dir.glob("checkpoint")) + list(model_dir.glob("*.index"))
    if checkpoint_markers:
        return

    archive = model_dir.parent / "e-gmd_checkpoint.zip"
    print(f"Downloading OaF E-GMD checkpoint to {archive}", flush=True)
    urllib.request.urlretrieve(CHECKPOINT_URL, archive)

    extract_dir = model_dir.parent / "_oaf_extract"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir()

    with zipfile.ZipFile(archive) as zf:
        zf.extractall(extract_dir)

    # Flatten the archive so --model_dir always points at the checkpoint files.
    all_files = [p for p in extract_dir.rglob("*") if p.is_file()]
    for source in all_files:
        relative = source.relative_to(extract_dir)
        target = model_dir / relative.name
        if target.exists():
            target.unlink()
        shutil.move(str(source), target)

    shutil.rmtree(extract_dir)
    archive.unlink(missing_ok=True)

    if not (model_dir / "checkpoint").exists() and not list(model_dir.glob("*.index")):
        raise RuntimeError(
            f"Checkpoint archive extracted, but no TensorFlow checkpoint was found in {model_dir}"
        )
