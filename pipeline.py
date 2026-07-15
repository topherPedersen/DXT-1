from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from groove import GrooveOptions, create_groove_midi

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineOptions:
    mode: Literal["full", "groove"] = "groove"
    groove_bars: int = 2
    groove_complexity: float = 0.55
    output_bars: int = 32
    phrase_markers: bool = True
    phrase_every_bars: int = 8
    demucs_model: str = "htdemucs"
    device: Literal["auto", "cpu", "cuda", "mps"] = "auto"


def run_command(command: list[str], cwd: Path | None = None) -> None:
    logger.info("Running: %s", " ".join(command))
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}:\n"
            f"{' '.join(command)}\n\n{completed.stdout[-8000:]}"
        )
    logger.info("%s", completed.stdout[-2000:])


def resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def separate_drums(
    input_path: Path,
    job_dir: Path,
    model: str,
    device: str,
) -> Path:
    separated_dir = job_dir / "separated"
    command = [
        sys.executable,
        "-m",
        "demucs",
        "--two-stems=drums",
        "-n",
        model,
        "-d",
        device,
        "-o",
        str(separated_dir),
        str(input_path),
    ]
    run_command(command)

    expected = separated_dir / model / input_path.stem / "drums.wav"
    if expected.exists():
        return expected

    candidates = list(separated_dir.rglob("drums.wav"))
    if len(candidates) == 1:
        return candidates[0]
    raise RuntimeError(
        "Demucs finished, but drums.wav could not be located. "
        f"Searched under {separated_dir}."
    )


def transcribe_drums(drum_audio_path: Path, output_midi_path: Path) -> None:
    try:
        from adtof_pytorch import transcribe_to_midi
    except ImportError as exc:
        raise RuntimeError(
            "ADTOF-PyTorch is not installed. Activate the project virtual "
            "environment and run ./install_mac.sh."
        ) from exc

    logger.info("Transcribing drum stem with ADTOF: %s", drum_audio_path)
    transcribe_to_midi(str(drum_audio_path), str(output_midi_path))

    if not output_midi_path.exists():
        raise RuntimeError("ADTOF completed without creating the expected MIDI file.")


def process_audio(
    input_path: Path,
    job_dir: Path,
    options: PipelineOptions,
) -> dict:
    device = resolve_device(options.device)
    drums_path = separate_drums(
        input_path=input_path,
        job_dir=job_dir,
        model=options.demucs_model,
        device=device,
    )

    full_midi_path = job_dir / "full_transcription.mid"
    transcribe_drums(drums_path, full_midi_path)

    if options.mode == "full":
        return {
            "midi_path": str(full_midi_path),
            "metadata": {
                "mode": "full",
                "device": device,
                "demucs_model": options.demucs_model,
                "drum_stem": drums_path.name,
            },
        }

    groove_midi_path = job_dir / "groove.mid"
    metadata = create_groove_midi(
        source_midi_path=full_midi_path,
        output_midi_path=groove_midi_path,
        options=GrooveOptions(
            bars=options.groove_bars,
            complexity=options.groove_complexity,
            output_bars=options.output_bars,
            add_phrase_markers=options.phrase_markers,
            phrase_every_bars=options.phrase_every_bars,
        ),
    )
    metadata.update({
        "device": device,
        "demucs_model": options.demucs_model,
        "drum_stem": drums_path.name,
    })
    return {
        "midi_path": str(groove_midi_path),
        "metadata": metadata,
    }
