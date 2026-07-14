from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from flask import Flask, jsonify, request

from checkpoint import ensure_checkpoint

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/models/oaf_drums"))
JOBS_DIR = Path(os.environ.get("JOBS_DIR", "/jobs"))

app = Flask(__name__)


def find_transcriber() -> list[str]:
    executable = shutil.which("onsets_frames_transcription_transcribe")
    if executable:
        return [executable]

    # Fallback for package installations that expose the module but not script.
    return [
        "python",
        "-m",
        "magenta.models.onsets_frames_transcription.onsets_frames_transcription_transcribe",
    ]


def find_new_midi(search_root: Path, started: float) -> Path:
    candidates = [
        p for p in search_root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in {".mid", ".midi"}
        and p.stat().st_mtime >= started - 2
    ]
    if not candidates:
        raise RuntimeError(
            "Magenta exited successfully but no new MIDI file was found. "
            f"Searched under {search_root}."
        )
    return max(candidates, key=lambda p: p.stat().st_mtime)


@app.get("/health")
def health():
    try:
        ensure_checkpoint(MODEL_DIR)
        return jsonify({"ok": True, "model_dir": str(MODEL_DIR)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/transcribe")
def transcribe():
    payload = request.get_json(force=True)
    job_id = Path(payload["job_id"]).name
    relative_audio = Path(payload["relative_audio_path"])

    job_dir = (JOBS_DIR / job_id).resolve()
    audio = (job_dir / relative_audio).resolve()

    if job_dir not in audio.parents:
        return jsonify({"error": "Audio path escapes the job directory."}), 400
    if not audio.exists():
        return jsonify({"error": f"Audio file does not exist: {audio}"}), 404

    try:
        ensure_checkpoint(MODEL_DIR)
        started = time.time()
        command = find_transcriber() + [
            f"--model_dir={MODEL_DIR}",
            "--config=drums",
            str(audio),
        ]
        result = subprocess.run(
            command,
            cwd=job_dir,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if result.returncode:
            return jsonify({
                "error": "OaF transcription command failed.",
                "command": command,
                "output": result.stdout[-12000:],
            }), 500

        produced = find_new_midi(job_dir, started)
        stable = job_dir / "oaf_raw.mid"
        if produced.resolve() != stable.resolve():
            shutil.copy2(produced, stable)

        return jsonify({
            "ok": True,
            "relative_midi_path": str(stable.relative_to(job_dir)),
            "command_output": result.stdout[-3000:],
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    ensure_checkpoint(MODEL_DIR)
    app.run(host="0.0.0.0", port=8011, threaded=False)
