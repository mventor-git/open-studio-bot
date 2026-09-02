"""URL verifier — stage 2 (T2 implementation).

Probes a URL with yt-dlp --dump-json --no-download. On login-walled
platforms (facebook/instagram/tiktok) retries with cookies copied from the
Waterfox profile (the live DB is locked while the browser runs).

Returns {ok, title, duration, cookies_used, error, probe: <raw metadata>}.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from config import config
from core.interrupt import registry

YTDLP = "yt-dlp"  # on PATH (validated 2026.07.04)

# Platforms that almost always need cookies
COOKIE_PLATFORMS = {"facebook", "instagram", "tiktok"}


def find_firefox_profile(platform_dir: Optional[Path] = None) -> Optional[Path]:
    """Locate a profile dir containing cookies.sqlite under the Waterfox profiles root."""
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


def _probe_once(url: str, job_id: str, cookiefile: Optional[Path] = None) -> tuple[Optional[dict], str]:
    """One yt-dlp probe attempt. Returns (metadata_dict | None, error_summary)."""
    args = [YTDLP, "--dump-json", "--no-download", "--no-warnings", url]
    if cookiefile is not None:
        args += ["--cookies", str(cookiefile)]
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    registry.register(job_id, proc)
    try:
        out, err = proc.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        proc.kill()
        return None, "probe timed out after 90s"
    finally:
        registry.unregister_proc(job_id, proc)

    if proc.returncode == 0 and out.strip():
        try:
            return json.loads(out.decode("utf-8", errors="replace")), ""
        except json.JSONDecodeError as exc:
            return None, f"probe output not JSON: {exc}"
    err_tail = (err or b"").decode("utf-8", errors="replace").strip().splitlines()
    return None, err_tail[-1] if err_tail else f"yt-dlp exited {proc.returncode}"


def verify_url(url: str, platform: str, job_id: str = "cli") -> dict[str, Any]:
    """Probe with fallback to Waterfox cookies for login-walled platforms."""
    result: dict[str, Any] = {
        "ok": False,
        "title": None,
        "duration": None,
        "cookies_used": False,
        "error": None,
        "probe": None,
    }

    meta, err = _probe_once(url, job_id)
    if meta is not None:
        result.update(ok=True, title=meta.get("title"), duration=meta.get("duration"), probe=meta)
        return result

    # First attempt failed — cookie fallback only makes sense for login walls
    if platform not in COOKIE_PLATFORMS:
        result["error"] = err
        return result

    tmpdir = copy_cookies_to_temp()
    if tmpdir is None:
        result["error"] = f"login wall and no Waterfox cookies found: {err}"
        return result

    try:
        cookiefile = tmpdir / "cookies.sqlite"
        meta2, err2 = _probe_once(url, job_id, cookiefile=cookiefile)
        if meta2 is not None:
            result.update(ok=True, title=meta2.get("title"), duration=meta2.get("duration"), cookies_used=True, probe=meta2)
            return result
        result["error"] = f"probe failed without and with cookies: {err2}"
        return result
    finally:
        # best-effort cleanup of temp cookie copy
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)
