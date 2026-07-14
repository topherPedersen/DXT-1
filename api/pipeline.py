from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import requests

from groove import GrooveOptions, create_groove_midi
from normalize import normalize_oaf_midi

logger = logging.getLogger(__name__)
OAF_URL = os.environ.get("OAF_URL", "http://oaf:8011")


@dataclass(frozen=True)
class PipelineOptions:
    mode: Literal["full", "groove"] = "groove"
    groove_bars: int = 2
    groove_complexity: float = 0.55
    output_bars: int = 32
    phrase_markers: bool = True
    phrase_every_bars: int = 8
    demucs_model: str = "htdemucs"


def run_command(command: list[str]) -> None:
    logger.info("Running: %s", " ".join(command))
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
    logger.info("%s", result.stdout[-2500:])


def separate_drums(input_path: Path, job_dir: Path, model: str) -> Path:
    if shutil.which("demucs") is None:
        raise RuntimeError("Demucs is not installed in the API container.")

    output_dir = job_dir / "separated"
    run_command([
        "demucs",
        "--two-stems=drums",
        "-n", model,
        "-d", "cpu",
        "-o", str(output_dir),
        str(input_path),
    ])

    expected = output_dir / model / input_path.stem / "drums.wav"
    if expected.exists():
        return expected

    candidates = list(output_dir.rglob("drums.wav"))
    if len(candidates) == 1:
        return candidates[0]
    raise RuntimeError("Demucs completed but drums.wav was not found.")


def call_oaf(job_dir: Path, drum_path: Path) -> Path:
    # Both containers mount the same job directory. Send paths relative to it.
    response = requests.post(
        f"{OAF_URL}/transcribe",
        json={
            "job_id": job_dir.name,
            "relative_audio_path": str(drum_path.relative_to(job_dir)),
        },
        timeout=60 * 60,
    )
    try:
        payload = response.json()
    except Exception:
        raise RuntimeError(
            f"OaF worker returned HTTP {response.status_code}: {response.text[-4000:]}"
        )

    if not response.ok:
        raise RuntimeError(payload.get("detail") or payload.get("error") or str(payload))

    midi_path = job_dir / payload["relative_midi_path"]
    if not midi_path.exists():
        raise RuntimeError(f"OaF reported MIDI that does not exist: {midi_path}")
    return midi_path


def process_audio(
    input_path: Path,
    job_dir: Path,
    options: PipelineOptions,
) -> dict:
    drums = separate_drums(input_path, job_dir, options.demucs_model)
    raw_oaf = call_oaf(job_dir, drums)

    normalized = job_dir / "oaf_rd8_full.mid"
    normalization = normalize_oaf_midi(raw_oaf, normalized)

    if options.mode == "full":
        return {
            "midi_path": str(normalized),
            "metadata": {
                "engine": "Magenta Onsets & Frames Drums",
                "mode": "full",
                "demucs_model": options.demucs_model,
                **normalization,
            },
        }

    groove_path = job_dir / "oaf_rd8_groove.mid"
    groove_metadata = create_groove_midi(
        normalized,
        groove_path,
        GrooveOptions(
            bars=options.groove_bars,
            complexity=options.groove_complexity,
            output_bars=options.output_bars,
            add_phrase_markers=options.phrase_markers,
            phrase_every_bars=options.phrase_every_bars,
        ),
    )
    return {
        "midi_path": str(groove_path),
        "metadata": {
            "engine": "Magenta Onsets & Frames Drums",
            "demucs_model": options.demucs_model,
            **normalization,
            **groove_metadata,
        },
    }
