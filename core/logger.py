"""CSV logger for jobs — UTF-8 with BOM for Excel Arabic support."""
from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "logs"
CSV_PATH = LOG_DIR / "jobs.csv"

# spec columns: timestamp, job_id, url, platform, template, status (done/failed/stopped/cancelled),
# title, duration, cut_start, cut_end, description, hashtags, handle, tiktok_handle, watermark_handle,
# output_path, tiktok_url, error, duration_seconds
COLUMNS = [
    "timestamp",
    "job_id",
    "url",
    "platform",
    "template",
    "status",
    "title",
    "duration",
    "cut_start",
    "cut_end",
    "description",
    "hashtags",
    "handle",
    "tiktok_handle",
    "watermark_handle",
    "output_path",
    "tiktok_url",
    "error",
    "duration_seconds",
]


def _ensure_log_file() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
        with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()


def log_job(job: dict[str, Any]) -> None:
    """Append one row for a terminal job. Safe to call multiple times; caller should ensure terminal state."""
    try:
        _ensure_log_file()
        # normalize fields
        result = job.get("result") or {}
        hashtags_val = job.get("hashtags", "")
        if isinstance(hashtags_val, list):
            hashtags_str = " ".join(hashtags_val)
        else:
            hashtags_str = str(hashtags_val or "")
        # handle fields
        handle = job.get("handle", "") or ""
        # tiktok/watermark from config fallback if not in job
        try:
            from config import config as _cfg

            tiktok_handle = job.get("tiktok_handle") or _cfg.tiktok_handle or ""
            watermark_handle = job.get("watermark_handle") or _cfg.watermark_handle or handle or ""
        except Exception:
            tiktok_handle = job.get("tiktok_handle", "") or ""
            watermark_handle = job.get("watermark_handle", "") or handle or ""
        # output_path priority
        output_path = (
            job.get("tiktok_path")
            or result.get("tiktok_path")
            or result.get("output_path")
            or job.get("video_path")
            or ""
        )
        tiktok_url = result.get("tiktok_url") or job.get("tiktok_url") or ""
        error = result.get("error") or job.get("error") or ""
        duration_val = job.get("duration") or result.get("duration") or ""
        # cut start/end
        cut_start = job.get("start")
        if cut_start is None:
            cut_start = job.get("cut_start", "")
        cut_end = job.get("end")
        if cut_end is None:
            cut_end = job.get("cut_end", "")
        # title
        title = job.get("title") or job.get("prompt") or ""
        description = job.get("description") or job.get("caption") or job.get("prompt") or ""
        platform = job.get("platform", "") or ""
        template = job.get("template", "") or ""
        status = job.get("state", "") or ""
        # normalize status: keep as is, but ensure cancelled/stopped mapping? keep original
        row = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "job_id": job.get("id", ""),
            "url": job.get("url", ""),
            "platform": platform,
            "template": template,
            "status": status,
            "title": title,
            "duration": str(duration_val) if duration_val != "" else "",
            "cut_start": str(cut_start) if cut_start not in (None, "") else "",
            "cut_end": str(cut_end) if cut_end not in (None, "") else "",
            "description": description,
            "hashtags": hashtags_str,
            "handle": handle,
            "tiktok_handle": tiktok_handle,
            "watermark_handle": watermark_handle,
            "output_path": str(output_path) if output_path else "",
            "tiktok_url": str(tiktok_url) if tiktok_url else "",
            "error": str(error) if error else "",
            "duration_seconds": str(duration_val) if duration_val != "" else "",
        }
        # utf-8-sig, quoting handles Arabic commas/quotes
        with open(CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
            writer.writerow(row)
    except Exception:
        # ponytail: logger must never crash the bot pipeline
        pass


def read_logs() -> list[dict[str, str]]:
    """Read back CSV for verification (handles BOM)."""
    if not CSV_PATH.exists():
        return []
    with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)
