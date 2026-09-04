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


def _is_login_wall_error(msg: str) -> bool:
    low = (msg or "").lower()
    markers = [
        "login", "sign in", "not logged in", "private video", "requires cookies",
        "this video is unavailable", "age-restricted", "confirm your age",
        "cookies", "access denied", "forbidden", "please log in",
    ]
    return any(m in low for m in markers)


def _cookie_health() -> tuple[bool, str, int, bool]:
    """Check tiktok cookies health: returns (ok, reason, count, has_sessionid)."""
    tmpdir = copy_cookies_to_temp()
    if tmpdir is None:
        return False, "no cookies.sqlite found", 0, False
    try:
        db = tmpdir / "cookies.sqlite"
        if not db.exists():
            return False, "cookies.sqlite missing in temp", 0, False
        import sqlite3
        import tempfile as _tf
        tmp = Path(_tf.gettempdir()) / f"ck_verify_{tmpdir.name}.sqlite"
        try:
            s_con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            d_con = sqlite3.connect(str(tmp))
            s_con.backup(d_con)
            d_con.close()
            s_con.close()
        except Exception:
            try:
                shutil.copy2(str(db), str(tmp))
            except Exception as e:
                return False, f"copy fail: {e}", 0, False
        con = sqlite3.connect(str(tmp))
        cur = con.cursor()
        try:
            cur.execute("SELECT name FROM moz_cookies WHERE host LIKE '%tiktok.com%'")
            rows = cur.fetchall()
        except Exception as e:
            con.close()
            try: tmp.unlink()
            except: pass
            return False, str(e), 0, False
        names = [r[0] for r in rows]
        cnt = len(names)
        has_sid = "sessionid" in names
        con.close()
        try: tmp.unlink()
        except: pass
        if cnt < 5:
            return False, f"cookies truncated: only {cnt} tiktok cookies (need >=5)", cnt, has_sid
        if not has_sid:
            return False, "cookies missing sessionid", cnt, has_sid
        return True, f"cookies OK {cnt}", cnt, has_sid
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except:
            pass


def verify_url(url: str, platform: str, job_id: str = "cli") -> dict[str, Any]:
    """Probe with fallback to Waterfox cookies for login-walled platforms."""
    result: dict[str, Any] = {
        "ok": False,
        "title": None,
        "duration": None,
        "cookies_used": False,
        "error": None,
        "probe": None,
        "cookie_fail": False,
        "cookie_reason": None,
    }

    # T7: early cookie health check for tiktok platform — fail fast if truncated
    if platform == "tiktok":
        ok, reason, cnt, has_sid = _cookie_health()
        if not ok:
            result["error"] = f"cookie fail: {reason} — ❌ TikTok session expired — please re-login in Waterfox at tiktok.com then send /retry or new URL"
            result["cookie_fail"] = True
            result["cookie_reason"] = reason
            # still try probe? No — cookie truncated means auth impossible, return early
            # but allow caller to send user-facing Telegram message
            return result

    meta, err = _probe_once(url, job_id)
    if meta is not None:
        result.update(ok=True, title=meta.get("title"), duration=meta.get("duration"), probe=meta)
        return result

    # check if first error looks like login wall
    if _is_login_wall_error(err):
        result["cookie_fail"] = True
        result["cookie_reason"] = err

    # First attempt failed — cookie fallback only makes sense for login walls
    if platform not in COOKIE_PLATFORMS:
        result["error"] = err
        # annotate cookie fail for tiktok even if not in platform? already handled
        if result.get("cookie_fail"):
            result["error"] = f"{err} — {config.tiktok_handle} session may be expired"
        return result

    tmpdir = copy_cookies_to_temp()
    if tmpdir is None:
        result["error"] = f"login wall and no Waterfox cookies found: {err}"
        result["cookie_fail"] = True
        result["cookie_reason"] = "no Waterfox cookies found"
        return result

    # also re-check health after copy
    try:
        # quick health via same helper but we already have tmpdir; reuse count check via DB in tmpdir
        import sqlite3
        cnt2 = 0
        has_sid2 = False
        try:
            db2 = tmpdir / "cookies.sqlite"
            tmp2 = Path(tempfile.gettempdir()) / f"ck_verify2_{tmpdir.name}.sqlite"
            try:
                s_con = sqlite3.connect(f"file:{db2}?mode=ro", uri=True, timeout=5)
                d_con = sqlite3.connect(str(tmp2))
                s_con.backup(d_con)
                d_con.close(); s_con.close()
            except Exception:
                shutil.copy2(str(db2), str(tmp2))
            con = sqlite3.connect(str(tmp2))
            cur = con.cursor()
            cur.execute("SELECT name FROM moz_cookies WHERE host LIKE '%tiktok.com%'")
            nms = [r[0] for r in cur.fetchall()]
            cnt2 = len(nms)
            has_sid2 = "sessionid" in nms
            con.close()
            try: tmp2.unlink()
            except: pass
        except Exception:
            pass
        if cnt2 < 5 or not has_sid2:
            result["error"] = f"cookie fail: truncated cookies count={cnt2} has_sessionid={has_sid2} — ❌ TikTok session expired — please re-login in Waterfox at tiktok.com then send /retry or new URL"
            result["cookie_fail"] = True
            result["cookie_reason"] = f"truncated {cnt2} has_sid={has_sid2}"
            return result
    except Exception:
        pass

    try:
        cookiefile = tmpdir / "cookies.sqlite"
        meta2, err2 = _probe_once(url, job_id, cookiefile=cookiefile)
        if meta2 is not None:
            result.update(ok=True, title=meta2.get("title"), duration=meta2.get("duration"), cookies_used=True, probe=meta2)
            # clear cookie_fail if probe succeeded with cookies
            result["cookie_fail"] = False
            result["cookie_reason"] = None
            return result
        if _is_login_wall_error(err2):
            result["cookie_fail"] = True
            result["cookie_reason"] = err2
            result["error"] = f"{err2} — cookie/session expired — ❌ TikTok session expired — please re-login in Waterfox at tiktok.com then send /retry or new URL"
            return result
        result["error"] = f"probe failed without and with cookies: {err2}"
        return result
    finally:
        # best-effort cleanup of temp cookie copy
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)
