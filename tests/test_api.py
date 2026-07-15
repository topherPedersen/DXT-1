from __future__ import annotations

import asyncio
import io
import tempfile
import unittest
from pathlib import Path

from fastapi import UploadFile

import app as app_module
from job_store import JobStore


class ApiJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.original_store = app_module.store
        self.original_jobs_dir = app_module.JOBS_DIR
        app_module.JOBS_DIR = root / "jobs"
        app_module.JOBS_DIR.mkdir()
        app_module.store = JobStore(root / "jobs.sqlite3")

    def tearDown(self) -> None:
        app_module.store = self.original_store
        app_module.JOBS_DIR = self.original_jobs_dir
        self.temporary_directory.cleanup()

    def test_upload_status_and_download_flow(self) -> None:
        upload = UploadFile(filename="purplehaze.mp3", file=io.BytesIO(b"test audio"))
        queued = asyncio.run(
            app_module.process(
                file=upload,
                mode="groove",
                groove_bars=2,
                groove_complexity=0.55,
                output_bars=32,
                phrase_markers=True,
                phrase_every_bars=8,
                demucs_model="htdemucs",
                device="auto",
            )
        )
        self.assertEqual(queued["status"], "queued")

        queued_status = app_module.job_status(queued["job_id"])
        self.assertEqual(queued_status["queue_position"], 1)

        job_id = queued["job_id"]
        claimed = app_module.store.claim_next()
        midi_path = app_module.JOBS_DIR / job_id / "groove.mid"
        midi_path.write_bytes(b"midi data")
        app_module.store.complete(claimed["id"], midi_path.name, {"bpm": 120})

        completed = app_module.job_status(job_id)
        self.assertEqual(completed["status"], "complete")
        self.assertEqual(completed["download_name"], "purplehaze.mid")

        download = app_module.download(job_id)
        self.assertEqual(Path(download.path).read_bytes(), b"midi data")
        self.assertIn("purplehaze.mid", download.headers["content-disposition"])


if __name__ == "__main__":
    unittest.main()
