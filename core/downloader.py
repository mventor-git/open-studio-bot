"""Downloader — stage 2 (T2 implementation).

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
from core.verifier import COOKIE_PLATFORMS, copy_cookies_to_temp as _copy_cookies

YTDLP = "yt-dlp"
_HEIGHT = {"360p": 360, "480p": 480, "720p": 720, "1080p": 1080}


def _ytdlp_cmd(args: list[str]) -> list[str]:
    return [YTDLP, *args]


def download(url: str, output_dir: Path, job_id: str, platform: str = "") -> dict[str, Any]:
    """Download capped at config.max_resolution. Returns {ok, video_path, error}.

    Killable mid-run via interrupt registry (terminate -> escalate kill).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    height = _HEIGHT.get(config.max_resolution, 720)
    fmt = (
        f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={height}]+bestaudio/"
        f"best[height<={height}][ext=mp4]/best[height<={height}]/"
        f"bestvideo+bestaudio/best"
    )

    def _attempt(cookiefile: Optional[Path]) -> tuple[bool, str]:
        args = [
            "--format", fmt,
            "--merge-output-format", "mp4",
            "--no-playlist",
            "--no-warnings",
            "--newline",
            "--print", "after_move:filepath",
            "-o", str(output_dir / "%(id)s.%(ext)s"),
            url,
        ]
        if cookiefile is not None:
            args += ["--cookies", str(cookiefile)]
        # ffmpeg/ffprobe live in our bundled tools dir — yt-dlp needs both
        # for stream merge (video+audio in one mp4) and postprocessing
        ffmpeg_bin = str(config.ffmpeg_dir)
        args += ["--ffmpeg-location", ffmpeg_bin]
        proc = subprocess.Popen(
            _ytdlp_cmd(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        registry.register(job_id, proc)
        try:
            out, err = proc.communicate(timeout=600)
        except subprocess.TimeoutExpired:
            proc.kill()
            return False, "download timed out after 600s"
        finally:
            registry.unregister_proc(job_id, proc)

        if proc.returncode != 0:
            err_tail = (err or b"").decode("utf-8", errors="replace").strip().splitlines()
            return False, err_tail[-1] if err_tail else f"yt-dlp exited {proc.returncode}"
        # --print after_move:filepath gives us the final file path on stdout
        lines = [ln.strip() for ln in out.decode("utf-8", errors="replace").splitlines() if ln.strip()]
        path = None
        for ln in reversed(lines):
            if ln and not ln.startswith("[") and Path(ln).exists():
                path = ln
                break
        if path is None:
            # fallback: newest media file in output dir
            media = [p for p in output_dir.iterdir() if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")]
            if not media:
                return False, "download reported success but no media file found"
            path = str(max(media, key=lambda p: p.stat().st_mtime))
        return True, path

    # Attempt 1: no cookies. Attempt 2 (login-walled platforms): Waterfox cookies.
    ok, info = _attempt(None)
    if not ok and platform in COOKIE_PLATFORMS:
        tmpdir = copy_cookies_to_temp()
        if tmpdir is not None:
            try:
                ok, info2 = _attempt(tmpdir / "cookies.sqlite")
                if ok:
                    info = info2
            finally:
                import shutil

                shutil.rmtree(tmpdir, ignore_errors=True)

    if not ok:
        return {"ok": False, "video_path": None, "error": info}

    # guard: downloaded file must actually contain a video stream
    # (yt-dlp can fall back to audio-only `best` on odd format mixes)
    streams = check_streams(info)
    if not streams.get("video_ok"):
        return {"ok": False, "video_path": info, "error": "downloaded file has no video stream (audio-only fallback)"}

    return {"ok": True, "video_path": info, "error": None, "streams": streams}


def check_streams(video_path: str | Path) -> dict[str, Any]:
    """ffprobe stream check -> {ok, video_ok, audio_ok, duration, width, height}."""
    ffprobe = config.ffmpeg_dir / "ffprobe.exe"
    if not ffprobe.exists():
        return {"ok": False, "video_ok": False, "audio_ok": False, "error": f"ffprobe missing: {ffprobe}"}
    proc = subprocess.run(
        [
            str(ffprobe),
            "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            str(video_path),
        ],
        capture_output=True,
        timeout=60,
    )
    if proc.returncode != 0:
        return {"ok": False, "video_ok": False, "audio_ok": False, "error": "ffprobe failed (corrupt file?)"}
    data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
    streams = data.get("streams", [])
    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    fmt = data.get("format", {})
    result = {
        "ok": bool(video),
        "video_ok": bool(video),
        "audio_ok": bool(audio),
        "duration": float(fmt.get("duration", 0) or 0),
        "width": video[0].get("width") if video else None,
        "height": video[0].get("height") if video else None,
    }
    return result


if __name__ == "__main__":
    # CLI: python -m core.downloader <url> [output_dir]
    import sys

    if len(sys.argv) < 2:
        print("usage: python -m core.downloader <url> [output_dir]")
        sys.exit(2)
    url = sys.argv[1]
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else config.jobs_dir / "cli-media"
    platform = ""
    from core.jobs import JobStore

    platform = JobStore.detect_platform(url) or ""

    print(f"[1/3] probing {url}")
    from core.verifier import verify_url

    v = verify_url(url, platform, job_id="cli")
    if not v["ok"]:
        print(f"VERIFY FAILED: {v['error']}")
        sys.exit(1)
    print(f"      title: {v['title']}")
    print(f"      duration: {v['duration']}s  cookies: {v['cookies_used']}")

    print("[2/3] downloading")
    d = download(url, out, job_id="cli", platform=platform)
    if not d["ok"]:
        print(f"DOWNLOAD FAILED: {d['error']}")
        sys.exit(1)
    print(f"      file: {d['video_path']}")

    print("[3/3] stream check")
    s = check_streams(d["video_path"])
    if not s["ok"]:
        print(f"STREAM CHECK FAILED: {s.get('error', 'no video stream')}")
        sys.exit(1)
    print(
        f"      video {'YES' if s['video_ok'] else 'NO'}  "
        f"sound {'YES' if s['audio_ok'] else 'NO'}  "
        f"{s['width']}x{s['height']}  {s['duration']:.1f}s"
    )
    print("OK")
