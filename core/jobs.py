"""Job store + state machine.

One job = one JSON file in jobs/: <id>.job.json (input+state).
Atomic writes (tmp + rename) so a killed process never corrupts state.
Single-job execution: only one job may be in an active state; others queue.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

# States
NEW = "new"
VERIFYING = "verifying"
VERIFIED = "verified"
DOWNLOADING = "downloading"
DOWNLOADED = "downloaded"
MONTAGING = "montaging"
WRITING_CAPTION = "writing_caption"
AWAITING_APPROVAL = "awaiting_approval"
UPLOADING = "uploading"
DONE = "done"
CANCELLED = "cancelled"
FAILED = "failed"

ACTIVE_STATES = {NEW, VERIFYING, VERIFIED, DOWNLOADING, DOWNLOADED, MONTAGING, WRITING_CAPTION, UPLOADING, AWAITING_APPROVAL}
TERMINAL_STATES = {DONE, CANCELLED, FAILED}

_PLATFORM_PATTERNS = [
    ("youtube", re.compile(r"(youtube\.com|youtu\.be)", re.I)),
    ("instagram", re.compile(r"instagram\.com", re.I)),
    ("facebook", re.compile(r"(facebook\.com|fb\.watch)", re.I)),
    ("tiktok", re.compile(r"tiktok\.com", re.I)),
]


class JobError(Exception):
    pass


class JobStore:
    def __init__(self, jobs_dir: Path) -> None:
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # --- helpers -------------------------------------------------------
    def _path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.job.json"

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def detect_platform(url: str) -> Optional[str]:
        for name, pattern in _PLATFORM_PATTERNS:
            if pattern.search(url):
                return name
        return None

    # --- api -----------------------------------------------------------
    def create(self, url: str, prompt: str = "", template: str = "") -> dict[str, Any]:
        platform = self.detect_platform(url)
        if platform is None:
            raise JobError("unsupported URL: expected youtube/instagram/facebook/tiktok link")
        job_id = f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
        job = {
            "id": job_id,
            "url": url,
            "platform": platform,
            "prompt": prompt.strip(),
            "template": template.strip(),
            "state": NEW,
            "video_path": None,
            "audio_ok": None,
            "result": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        with self._lock:
            self._atomic_write(self._path(job_id), job)
        return job

    def load(self, job_id: str) -> dict[str, Any]:
        path = self._path(job_id)
        if not path.exists():
            raise JobError(f"job not found: {job_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def update(self, job: dict[str, Any], **fields: Any) -> dict[str, Any]:
        job.update(fields)
        job["updated_at"] = time.time()
        with self._lock:
            self._atomic_write(self._path(job["id"]), job)
        return job

    def set_state(self, job: dict[str, Any], state: str) -> dict[str, Any]:
        if state not in ACTIVE_STATES | TERMINAL_STATES:
            raise JobError(f"unknown state: {state}")
        return self.update(job, state=state)

    def active_job(self) -> Optional[dict[str, Any]]:
        """Oldest active job by creation time (queue order), not filename order."""
        actives = [j for j in self._all() if j.get("state") in ACTIVE_STATES]
        if not actives:
            return None
        return min(actives, key=lambda j: (j.get("created_at", 0), j.get("id", "")))

    def queued(self) -> list[dict[str, Any]]:
        return [j for j in self._all() if j.get("state") == NEW]

    def _all(self) -> list[dict[str, Any]]:
        jobs = []
        for path in sorted(self.jobs_dir.glob("*.job.json")):
            try:
                jobs.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return jobs


def interruptible(job: dict[str, Any]) -> bool:
    """Whether a job may be cancelled right now (upload start is gated elsewhere)."""
    return job.get("state") not in TERMINAL_STATES
