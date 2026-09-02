"""Downloader — stage 2 (T2).

Contract (per ticket T2):
- yt-dlp subprocess, CREATE_NEW_PROCESS_GROUP so terminate() works on Windows
- resolution cap from config.max_resolution (default 720p)
- after download: ffprobe stream check -> {video_ok, audio_ok}
- every subprocess registered with interrupt registry; killable mid-run
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Optional

from config import config
from core.interrupt import registry


def _run_ytdlp(args: list[str], job_id: str) -> subprocess.Popen:
    """Start a killable yt-dlp process (T2 fills in real invocation points)."""
    proc = subprocess.Popen(
        ["yt-dlp", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,  # Windows killable
    )
    registry.register(job_id, proc)
    return proc


def probe(url: str, job_id: str) -> Optional[dict[str, Any]]:
    """yt-dlp --dump-json --no-download. T2 implements retry-with-cookies."""
    raise NotImplementedError("T2: probe")


def download(url: str, output_dir: Path, job_id: str) -> dict[str, Any]:
    """Download capped at config.max_resolution. T2 implements."""
    raise NotImplementedError("T2: download")


def check_streams(video_path: Path) -> dict[str, bool]:
    """ffprobe stream check. T2 implements full parsing."""
    raise NotImplementedError("T2: ffprobe check")
