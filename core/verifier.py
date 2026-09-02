"""URL verifier — stage 1.

Platform detection happens in core.jobs (regex). This module probes the URL
with yt-dlp (--dump-json --no-download) to confirm it is real and extract
metadata. On login-walled platforms (facebook/instagram/tiktok) it retries
with cookies copied from the Waterfox profile.

T2 implements the real probe; this file holds the contract + helpers.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Optional

from config import config

# Platforms that almost always need cookies
COOKIE_PLATFORMS = {"facebook", "instagram", "tiktok"}


def find_firefox_profile(platform_dir: Optional[Path] = None) -> Optional[Path]:
    """Locate a default-release-style profile dir under the Waterfox profiles root."""
    root = platform_dir if platform_dir is not None else config.waterfox_profile
    if not root.exists():
        return None
    candidates = sorted(root.glob("*.default-release*")) or sorted(root.glob("*"))
    for cand in candidates:
        if (cand / "cookies.sqlite").exists():
            return cand
    return None


def copy_cookies_to_temp() -> Optional[Path]:
    """Copy cookies.sqlite (+ .wal) to temp — yt-dlp can't read the live locked DB.

    The Waterfox profile database is locked while the browser runs; a copy
    sidesteps that. Caller is responsible for cleanup (temp dir).
    """
    profile = find_firefox_profile()
    if profile is None:
        return None
    tmpdir = Path(tempfile.mkdtemp(prefix="tg-montage-cookies-"))
    copied = False
    for name in ("cookies.sqlite", "cookies.sqlite-wal"):
        src = profile / name
        if src.exists():
            shutil.copy2(src, tmpdir / name)
            copied = True
    return tmpdir if copied else None


def verify_url(url: str, platform: str) -> dict:
    """Probe the URL. T2 will implement: yt-dlp --dump-json, cookie fallback.

    Returns {ok, title, duration, cookies_used, error}.
    """
    raise NotImplementedError("T2: verifier probe")
