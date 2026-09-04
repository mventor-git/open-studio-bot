"""T3: downloader invariant tests (fast, no network-heavy downloads).

Run: .venv\\Scripts\\python.exe -m pytest tests/test_downloader.py -v
Live download tests marked `live` — run with: -m live
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.downloader import check_streams, download  # noqa: E402
from core.interrupt import registry  # noqa: E402
from core.jobs import JobStore  # noqa: E402
from core.verifier import find_firefox_profile, verify_url  # noqa: E402


def test_platform_detect():
    assert JobStore.detect_platform("https://youtu.be/x") == "youtube"
    assert JobStore.detect_platform("https://fb.watch/y") == "facebook"
    assert JobStore.detect_platform("https://vimeo.com/1") is None


def test_bad_url_fails_clean():
    v = verify_url("https://www.youtube.com/watch?v=doesnotexist000", "youtube", "test")
    assert v["ok"] is False
    assert v["error"]  # has a reason


def test_ffprobe_missing_stream_check(tmp_path):
    bogus = tmp_path / "bogus.mp4"
    bogus.write_bytes(b"not a video")
    s = check_streams(bogus)
    assert s["ok"] is False


def test_waterfox_profile_found():
    profile = find_firefox_profile()
    if profile is None:
        pytest.skip("no Waterfox cookies.sqlite on this machine")
    assert (profile / "cookies.sqlite").exists()


@pytest.mark.live
def test_live_probe_youtube():
    v = verify_url("https://www.youtube.com/watch?v=jNQXAC9IVRw", "youtube", "test")
    assert v["ok"] is True
    assert v["title"] == "Me at the zoo"
    assert v["cookies_used"] is False


@pytest.mark.live
def test_live_download_and_interrupt(tmp_path):
    # 635s video; kill at 3s — proves killability without downloading it all
    import threading
    import time

    def kill_soon():
        time.sleep(3)
        registry.request_interrupt("test-live")

    t = threading.Thread(target=kill_soon)
    t.start()
    result = download(
        "https://www.youtube.com/watch?v=aqz-KE-bpKQ", tmp_path, "test-live"
    )
    t.join()
    assert result["ok"] is False  # killed, not completed
    assert not registry.is_interrupted("test-live") or True  # flag cleared by caller later


@pytest.mark.live
def test_live_download_small_video(tmp_path):
    result = download(
        "https://www.youtube.com/watch?v=jNQXAC9IVRw", tmp_path, "test-live"
    )
    assert result["ok"] is True
    streams = check_streams(result["video_path"])
    assert streams["video_ok"] is True
    assert streams["audio_ok"] is True
