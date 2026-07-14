from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.transcriber import CustomDrumTranscriber


def run(command):
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n\n"
            f"{result.stdout[-10000:]}"
        )


def separate_drums(input_path: Path, job_dir: Path) -> Path:
    if shutil.which("demucs") is None:
        raise RuntimeError("Demucs is not installed.")
    output = job_dir / "separated"
    run([
        "demucs",
        "--two-stems=drums",
        "-n", "htdemucs",
        "-d", "cpu",
        "-o", str(output),
        str(input_path),
    ])
    candidates = list(output.rglob("drums.wav"))
    if len(candidates) != 1:
        raise RuntimeError("Could not locate the separated drums.wav.")
    return candidates[0]


def process(input_path, job_dir, model_path):
    drums = separate_drums(input_path, job_dir)
    midi = job_dir / "custom_rd8.mid"
    metadata = CustomDrumTranscriber(model_path).transcribe(drums, midi)
    return midi, metadata
