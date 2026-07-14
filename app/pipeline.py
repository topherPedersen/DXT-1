from __future__ import annotations
import subprocess
import sys
from pathlib import Path

from .midi_utils import midi_to_events

class PipelineError(RuntimeError):
    pass

def run_command(command: list[str], cwd: Path | None = None) -> None:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if completed.returncode != 0:
        raise PipelineError(
            f"Command failed ({completed.returncode}): {' '.join(command)}\n\n"
            f"STDOUT:\n{completed.stdout[-4000:]}\n\nSTDERR:\n{completed.stderr[-4000:]}"
        )

def separate_drums(source: Path, output_dir: Path, model: str = "htdemucs") -> Path:
    # Use the module invocation so the executable does not need to be on PATH.
    run_command([
        sys.executable, "-m", "demucs.separate",
        "--two-stems", "drums",
        "-n", model,
        "-o", str(output_dir),
        str(source),
    ])
    expected = output_dir / model / source.stem / "drums.wav"
    if expected.exists():
        return expected
    candidates = list(output_dir.rglob("drums.wav"))
    if not candidates:
        raise PipelineError("Demucs completed, but drums.wav was not found.")
    return candidates[0]

def transcribe_adtof(drums_wav: Path, output_midi: Path, thresholds: str | None = None, device: str = "cpu") -> None:
    # Direct, documented programmatic API. Fall back to its documented CLI so an
    # upstream packaging change gives a useful path rather than a cryptic import error.
    try:
        from adtof_pytorch import transcribe_to_midi
        kwargs = {}
        # Keep the first version on model defaults. User-tunable thresholds are passed
        # through the CLI because upstream API keyword names may evolve.
        if thresholds is None:
            transcribe_to_midi(str(drums_wav), str(output_midi))
            return
    except Exception as api_error:
        if thresholds is None:
            api_message = repr(api_error)
        else:
            api_message = "threshold override requested"

    command = ["adtof", "--audio", str(drums_wav), "--out", str(output_midi), "--device", device]
    if thresholds:
        command += ["--thresholds", thresholds]
    try:
        run_command(command)
    except Exception as cli_error:
        raise PipelineError(f"ADTOF API failed ({api_message}); CLI also failed: {cli_error}") from cli_error


def process_audio(source: Path, job_dir: Path, skip_demucs: bool = False, demucs_model: str = "htdemucs", thresholds: str | None = None, device: str = "cpu"):
    stem_dir = job_dir / "separated"
    drums_wav = source if skip_demucs else separate_drums(source, stem_dir, demucs_model)
    raw_midi = job_dir / "adtof-raw.mid"
    transcribe_adtof(drums_wav, raw_midi, thresholds=thresholds, device=device)
    events = midi_to_events(raw_midi)
    return drums_wav, raw_midi, events
