from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from job_store import JobStore, QueueFullError


class JobStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = JobStore(Path(self.temporary_directory.name) / "jobs.sqlite3")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def enqueue(self, job_id: str) -> None:
        self.store.enqueue(
            job_id=job_id,
            original_name="purplehaze.mp3",
            download_name="purplehaze.mid",
            mode="groove",
            options={"mode": "groove", "groove_bars": 2},
        )

    def test_jobs_are_claimed_once_in_queue_order(self) -> None:
        first_id = "1" * 32
        second_id = "2" * 32
        self.enqueue(first_id)
        self.enqueue(second_id)

        self.assertEqual(self.store.queue_position(first_id), 1)
        self.assertEqual(self.store.queue_position(second_id), 2)
        self.assertEqual(self.store.claim_next()["id"], first_id)
        self.assertEqual(self.store.claim_next()["id"], second_id)
        self.assertIsNone(self.store.claim_next())

    def test_completed_job_keeps_download_name_and_metadata(self) -> None:
        job_id = "a" * 32
        self.enqueue(job_id)
        self.store.claim_next()
        self.store.complete(job_id, "groove.mid", {"bpm": 120})

        job = self.store.get(job_id)
        self.assertEqual(job["status"], "complete")
        self.assertEqual(job["download_name"], "purplehaze.mid")
        self.assertEqual(job["midi_filename"], "groove.mid")
        self.assertEqual(job["metadata"], {"bpm": 120})

    def test_failed_job_records_error(self) -> None:
        job_id = "b" * 32
        self.enqueue(job_id)
        self.store.claim_next()
        self.store.fail(job_id, "conversion failed")

        job = self.store.get(job_id)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error"], "conversion failed")

    def test_queue_capacity_is_enforced_atomically(self) -> None:
        self.store.enqueue(
            job_id="c" * 32,
            original_name="one.mp3",
            download_name="one.mid",
            mode="groove",
            options={"mode": "groove"},
            max_active_jobs=1,
        )
        with self.assertRaises(QueueFullError):
            self.store.enqueue(
                job_id="d" * 32,
                original_name="two.mp3",
                download_name="two.mid",
                mode="groove",
                options={"mode": "groove"},
                max_active_jobs=1,
            )


if __name__ == "__main__":
    unittest.main()
