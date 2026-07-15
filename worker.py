from __future__ import annotations

import logging
import os
import shutil
import signal
import time
from pathlib import Path

from job_store import JobStore
from pipeline import PipelineOptions, process_audio

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DXT_DATA_DIR", BASE_DIR / "data")).expanduser().resolve()
JOBS_DIR = DATA_DIR / "jobs"
DATABASE_PATH = DATA_DIR / "jobs.sqlite3"
POLL_SECONDS = float(os.getenv("DXT_WORKER_POLL_SECONDS", "1"))
RETENTION_HOURS = max(1, int(os.getenv("DXT_JOB_RETENTION_HOURS", "24")))
STALE_JOB_HOURS = max(1, int(os.getenv("DXT_STALE_JOB_HOURS", "6")))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("dxt-worker")
store = JobStore(DATABASE_PATH)
running = True


def request_shutdown(_signum: int, _frame: object) -> None:
    global running
    running = False


def clean_expired_jobs() -> None:
    for job_id in store.expired_terminal_jobs(RETENTION_HOURS):
        shutil.rmtree(JOBS_DIR / job_id, ignore_errors=True)
        store.delete(job_id)
        logger.info("Deleted expired job %s", job_id)


def process_job(job: dict) -> None:
    job_id = job["id"]
    job_dir = JOBS_DIR / job_id
    input_candidates = list(job_dir.glob("source.*"))
    if len(input_candidates) != 1:
        raise RuntimeError("The queued source file is missing.")

    options = PipelineOptions(**job["options"])
    result = process_audio(input_candidates[0], job_dir, options)
    midi_filename = Path(result["midi_path"]).name
    store.complete(job_id, midi_filename, result["metadata"])
    logger.info("Completed job %s", job_id)


def main() -> None:
    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    logger.info("DXT worker started; completed files are retained for %s hours", RETENTION_HOURS)
    recovered = store.requeue_stale_processing(STALE_JOB_HOURS)
    if recovered:
        logger.warning("Recovered %s stale processing job(s)", recovered)
    clean_expired_jobs()

    completed_since_cleanup = 0
    while running:
        job = store.claim_next()
        if job is None:
            time.sleep(POLL_SECONDS)
            continue
        try:
            logger.info("Processing job %s", job["id"])
            process_job(job)
        except Exception as exc:
            logger.exception("Job %s failed", job["id"])
            store.fail(job["id"], str(exc))
        completed_since_cleanup += 1
        if completed_since_cleanup >= 10:
            clean_expired_jobs()
            completed_since_cleanup = 0

    logger.info("DXT worker stopped")


if __name__ == "__main__":
    main()
