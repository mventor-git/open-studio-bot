"""Selftests for T1 (stdlib only): run with `python -m tests.selftest`.

Covers the invariants that must hold before T2/T4 build on top:
- platform detection regexes
- job create/load/update/set_state round-trip (atomic files on disk)
- single-active-job semantics
- interrupt flag + kill-registry behavior (with a real sleep process)
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.interrupt import InterruptRegistry
from core.jobs import (
    ACTIVE_STATES,
    DOWNLOADED,
    DOWNLOADING,
    FAILED,
    JobStore,
    NEW,
    UPLOADING,
)


def test_platform_detection() -> None:
    cases = {
        "https://youtu.be/abc123": "youtube",
        "https://www.youtube.com/watch?v=x": "youtube",
        "https://www.instagram.com/reel/xyz/": "instagram",
        "https://www.facebook.com/watch/?v=123": "facebook",
        "https://fb.watch/abc/": "facebook",
        "https://www.tiktok.com/@user/video/999": "tiktok",
    }
    for url, expected in cases.items():
        got = JobStore.detect_platform(url)
        assert got == expected, f"{url}: expected {expected}, got {got}"
    assert JobStore.detect_platform("https://vimeo.com/123") is None
    print("  platform detection OK")


def test_job_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = JobStore(Path(tmp))
        job = store.create("https://www.facebook.com/watch/?v=123", prompt="make it dramatic", template="cinematic-dark")
        assert job["platform"] == "facebook"
        assert job["state"] == NEW

        loaded = store.load(job["id"])
        assert loaded["prompt"] == "make it dramatic"

        store.set_state(loaded, DOWNLOADING)
        reloaded = store.load(job["id"])
        assert reloaded["state"] == DOWNLOADING
        assert reloaded["updated_at"] >= reloaded["created_at"]
    print("  job roundtrip OK")


def test_single_active_job() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = JobStore(Path(tmp))
        first = store.create("https://youtu.be/a")
        second = store.create("https://youtu.be/b")
        # oldest active job wins (queue order)
        assert store.active_job()["id"] == first["id"]
        # once first finishes, second becomes active
        done_job = store.load(first["id"])
        store.set_state(done_job, FAILED)
        assert store.active_job()["id"] == second["id"]
        _ = second
    print("  single-active semantics OK")


def test_interrupt_registry() -> None:
    reg = InterruptRegistry()
    # a real, killable process (sleep) to prove terminate() works
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    reg.register("job1", proc)
    assert reg.should_proceed("job1")
    killed = reg.request_interrupt("job1")
    assert killed is True, "expected the running process to be killed"
    assert proc.poll() is not None, "process should be terminated"
    assert not reg.should_proceed("job1")

    # flag-only path (no process)
    reg2 = InterruptRegistry()
    reg2.request_interrupt("job2")
    assert not reg2.should_proceed("job2")
    reg2.clear("job2")
    assert reg2.should_proceed("job2")
    print("  interrupt registry OK")


def test_active_states_membership() -> None:
    # guard against typos in the state sets
    for s in (NEW, DOWNLOADING, UPLOADING):
        assert s in ACTIVE_STATES
    assert FAILED not in ACTIVE_STATES
    print("  state sets OK")


def main() -> int:
    print("T1 selftests:")
    test_platform_detection()
    test_job_roundtrip()
    test_single_active_job()
    test_interrupt_registry()
    test_active_states_membership()
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
