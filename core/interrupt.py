"""Interrupt registry — cancel support for every stage.

Pattern: request_interrupt(job_id) sets a flag; every long-running stage
checks should_proceed(job_id) before/while working, and registers its
subprocess handles here so terminate() can kill them.
"""
from __future__ import annotations

import subprocess
import threading
from typing import Optional


class InterruptRegistry:
    def __init__(self) -> None:
        self._flags: dict[str, threading.Event] = {}
        self._procs: dict[str, list[subprocess.Popen]] = {}
        self._lock = threading.Lock()

    def request_interrupt(self, job_id: str, wait_timeout: float = 5.0) -> bool:
        """Mark job for cancellation. Returns True if a running process was killed.

        terminate() is async on Windows — waits up to wait_timeout for exit,
        escalating to kill() if needed.
        """
        with self._lock:
            flag = self._flags.setdefault(job_id, threading.Event())
            flag.set()
            procs = self._procs.pop(job_id, [])
        killed = False
        for proc in procs:
            if proc.poll() is None:  # still running
                try:
                    proc.terminate()
                    killed = True
                    try:
                        proc.wait(timeout=wait_timeout)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=wait_timeout)
                except OSError:
                    pass
        return killed

    def is_interrupted(self, job_id: str) -> bool:
        with self._lock:
            flag = self._flags.get(job_id)
            return bool(flag and flag.is_set())

    def register(self, job_id: str, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.setdefault(job_id, []).append(proc)

    def unregister_proc(self, job_id: str, proc: subprocess.Popen) -> None:
        with self._lock:
            procs = self._procs.get(job_id, [])
            if proc in procs:
                procs.remove(proc)

    def should_proceed(self, job_id: str) -> bool:
        """Stages call this between steps; False = stop and mark cancelled."""
        return not self.is_interrupted(job_id)

    def clear(self, job_id: str) -> None:
        with self._lock:
            self._flags.pop(job_id, None)
            self._procs.pop(job_id, None)


registry = InterruptRegistry()
