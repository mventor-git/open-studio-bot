"""tg-montage bot entry point — T6 wiring.

Run modes:
  python bot.py                 # long polling (requires BOT_TOKEN)
  python bot.py --check-config  # validate config and exit (T1 acceptance)
  python bot.py --dry-run       # handler parsing self-check, no Telegram needed

Flow T6:
  user sends URL + optional cut + Template 01/00 + description
   -> verify -> download (with --download-sections if cut) -> vertical_fast (9:16, Majalla card for 01, clean for 00) -> upload TikTok
   Template 01 = 9:16 + Majalla card 0.94w 1.95×h + @mventor; Template 00 = same 9:16 but no card burned, desc only as post text.
   Progress edits same message + final post link + video document.

Only ALLOWED_CHAT_ID (7830528991) may trigger jobs. Handler is async, long jobs via asyncio.create_task.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from config import check_config, config

# --- parsing helpers (pure, testable without Telegram) -----------------

DEFAULT_TITLE = "سعدني في الحضارة"
DEFAULT_SUBTITLE = "صفات القائد"

_ALLOWED_DOMAINS = ("youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com", "fb.watch")


def _extract_url(text: str) -> str | None:
    pat = re.compile(r"https?://[^\s]+")
    for cand in pat.findall(text or ""):
        stripped = cand.rstrip('.,)]}>"\'!?')
        low = stripped.lower()
        if any(d in low for d in _ALLOWED_DOMAINS):
            return stripped
    return None


def _colon_to_sec(m: str, s: str) -> int:
    return int(m) * 60 + int(s)


def _dot_to_sec(m: str, s: str) -> int:
    return int(m) * 60 + int(s)


def _fmt_secs(sec: int) -> str:
    sec = int(sec)
    if sec >= 3600:
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        return f"{h}:{m:02d}:{s:02d}"
    m = sec // 60
    s = sec % 60
    return f"{m}:{s:02d}"


def parse_time_cut(text: str) -> tuple[int | None, int | None, str | None]:
    """Return (start_sec, end_sec, raw_match) or (None,None,None)."""
    if not text:
        return None, None, None
    # 1) colon pair: 26:19 to 27:10, 0:25-1:00, 26:19-27:10
    m = re.search(r"(\d{1,3}):(\d{2})\s*(?:to|\-|\u2013|–)\s*(\d{1,3}):(\d{2})", text, re.I)
    if m:
        s = _colon_to_sec(m.group(1), m.group(2))
        e = _colon_to_sec(m.group(3), m.group(4))
        return s, e, m.group(0)
    # 2) dot pair: 0.25 to 1.00, 0.25-1.00
    m = re.search(r"(\d+)\.(\d{1,2})\s*(?:to|\-|\u2013|–)\s*(\d+)\.(\d{1,2})", text, re.I)
    if m:
        s = _dot_to_sec(m.group(1), m.group(2))
        e = _dot_to_sec(m.group(3), m.group(4))
        return s, e, m.group(0)
    # 3) t= param: t=702s or &t=702 or ?t=702s
    m = re.search(r"[?&]t=(\d+)", text, re.I)
    if m:
        return int(m.group(1)), None, m.group(0)
    m = re.search(r"\bt\s*=\s*(\d+)\s*s\b", text, re.I)
    if m:
        return int(m.group(1)), None, m.group(0)
    return None, None, None


def parse_template(text: str) -> str:
    m = re.search(r"template\s*0?\s*(\d{1,2})", text or "", re.I)
    if m:
        num = m.group(1).lstrip("0") or "0"
        # spec expects 01 for template 1, 00 for template 00 (no card)
        return num.zfill(2)
    return "01"


def _has_no_watermark(text: str) -> bool:
    return bool(re.search(r"no[\s\-_]*watermark|--no-watermark|without watermark", text or "", re.I))


def _extract_raw_caption(text: str, url: str | None) -> str:
    """Caption for Template 00: raw Description: value or trailing text, else empty (no defaults)."""
    raw_text = text or ""
    m = re.search(r"description\s+is\s*:\s*(.*)", raw_text, re.I | re.S)
    if m:
        raw = m.group(1).strip()
        raw = re.sub(r"^\s*template\s*0?\s*\d+\s*[-–—]*\s*", "", raw, flags=re.I)
        cleaned = _strip_cuts(raw)
        cleaned = re.sub(r"template\s*0?\s*\d+", "", cleaned, flags=re.I)
        cleaned = re.sub(r"no[\s\-_]*watermark|--no-watermark|without watermark", "", cleaned, flags=re.I)
        cleaned = cleaned.strip(" \t\n\r-–—,;:\"'").strip()
        cleaned = re.sub(r"^[\s\-–—]+", "", cleaned).strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned.strip()
    if url and url in raw_text:
        rest = raw_text.split(url, 1)[1]
    else:
        rest = raw_text
    cleaned = _strip_cuts(rest)
    cleaned = re.sub(r"template\s*0?\s*\d+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"no[\s\-_]*watermark|--no-watermark|without watermark", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^\s*[-–—,;:\s]+", "", cleaned)
    cleaned = re.sub(r"\s*[-–—,;:\s]+$", "", cleaned)
    cleaned = cleaned.strip(" \t\n\r-–—,;:\"'").strip()
    cleaned = re.sub(r"^[\s\-–—]+", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"^(-\s*)+", "", cleaned).strip()
    return cleaned.strip()


def _strip_cuts(text: str) -> str:
    pats = [
        r"\bcut\s*\d{1,3}:\d{2}\s*(?:to|\-|\u2013|–)\s*\d{1,3}:\d{2}\b",
        r"\bcut\s*\d+\.\d{1,2}\s*(?:to|\-|\u2013|–)\s*\d+\.\d{1,2}\b",
        r"\d{1,3}:\d{2}\s*(?:to|\-|\u2013|–)\s*\d{1,3}:\d{2}",
        r"\d+\.\d{1,2}\s*(?:to|\-|\u2013|–)\s*\d+\.\d{1,2}",
        r"\bt\s*=\s*\d+\s*s\b",
        r"[?&]t=\d+s?\b",
    ]
    out = text
    for pat in pats:
        out = re.sub(pat, "", out, flags=re.I)
    return out


def parse_description(text: str, url: str | None) -> tuple[str, str, str]:
    """Return (title, subtitle, caption). Falls back to defaults if no user caption."""
    raw_text = text or ""
    # case A: "description is : ..."
    m = re.search(r"description\s+is\s*:\s*(.*)", raw_text, re.I | re.S)
    if m:
        raw = m.group(1).strip()
        # remove leading Template 01 prefix
        raw = re.sub(r"^\s*template\s*0?\s*\d+\s*[-–—]*\s*", "", raw, flags=re.I)
        cleaned = _strip_cuts(raw)
        cleaned = re.sub(r"template\s*0?\s*\d+", "", cleaned, flags=re.I)
        cleaned = cleaned.strip(" \t\n\r-–—,;:\"'").strip()
        cleaned = re.sub(r"^[\s\-–—]+", "", cleaned).strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            if " - " in cleaned or " – " in cleaned or " — " in cleaned:
                parts = re.split(r"\s*[-–—]\s*", cleaned, maxsplit=1)
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) >= 2:
                    return parts[0], parts[1], cleaned
                return parts[0], DEFAULT_SUBTITLE, cleaned
            return cleaned, DEFAULT_SUBTITLE, cleaned
        return DEFAULT_TITLE, DEFAULT_SUBTITLE, f"{DEFAULT_TITLE} - {DEFAULT_SUBTITLE}"
    # case B: remainder after URL
    if url and url in raw_text:
        rest = raw_text.split(url, 1)[1]
    else:
        rest = raw_text
    cleaned = _strip_cuts(rest)
    cleaned = re.sub(r"template\s*0?\s*\d+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^\s*[-–—,;:\s]+", "", cleaned)
    cleaned = re.sub(r"\s*[-–—,;:\s]+$", "", cleaned)
    cleaned = cleaned.strip(" \t\n\r-–—,;:\"'").strip()
    cleaned = re.sub(r"^[\s\-–—]+", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # remove stray leading dash combos like " - - "
    cleaned = re.sub(r"^(-\s*)+", "", cleaned).strip()
    if cleaned:
        if " - " in cleaned or " – " in cleaned or " — " in cleaned:
            parts = re.split(r"\s*[-–—]\s*", cleaned, maxsplit=1)
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) >= 2:
                return parts[0], parts[1], cleaned
            return parts[0], DEFAULT_SUBTITLE, cleaned
        return cleaned, DEFAULT_SUBTITLE, cleaned
    return DEFAULT_TITLE, DEFAULT_SUBTITLE, f"{DEFAULT_TITLE} - {DEFAULT_SUBTITLE}"


def parse_message(text: str) -> dict:
    """Parse Telegram message text into job params.

    Returns dict with url, start, end, template, title, subtitle, caption, raw_cut, handle.
    Template 00: no burned card — title/subtitle forced empty, caption is raw Description: if any else "".
    Watermark: default @mventor unless text contains no watermark / --no-watermark.
    """
    url = _extract_url(text)
    start, end, raw_cut = parse_time_cut(text)
    template = parse_template(text)
    handle = "" if _has_no_watermark(text) else "@mventor"
    if template == "00":
        caption = _extract_raw_caption(text, url)
        title = ""
        subtitle = ""
    else:
        title, subtitle, caption = parse_description(text, url)
        # strip watermark phrase from caption/title if user typed it (so it doesn't burn into card)
        if _has_no_watermark(text):
            # clean caption of watermark remnants
            caption = re.sub(r"no[\s\-_]*watermark|--no-watermark|without watermark", "", caption, flags=re.I).strip()
            caption = re.sub(r"\s+", " ", caption).strip(" -–—,;:")
            title = re.sub(r"no[\s\-_]*watermark|--no-watermark|without watermark", "", title, flags=re.I).strip()
            subtitle = re.sub(r"no[\s\-_]*watermark|--no-watermark|without watermark", "", subtitle, flags=re.I).strip()
    return {
        "url": url,
        "start": start,
        "end": end,
        "raw_cut": raw_cut,
        "template": template,
        "title": title,
        "subtitle": subtitle,
        "caption": caption,
        "handle": handle,
    }


# --- dry-run self-check ------------------------------------------------

def dry_run_mode() -> int:
    print("dry-run: parsing handler checks")
    cases = [
        (
            "https://www.youtube.com/watch?v=xZDk-vyZm3w - Cut 26:19 to 27:10 Template 01 - سعدني في الحضارة",
            {"url": "https://www.youtube.com/watch?v=xZDk-vyZm3w", "start": 1579, "end": 1630, "template": "01", "title_contains": "سعدني"},
        ),
        (
            "https://www.youtube.com/watch?v=IvaxAtX4abc Template 01 - Cut 0.25 to 1.00",
            {"url": "https://www.youtube.com/watch?v=IvaxAtX4abc", "start": 25, "end": 60, "template": "01"},
        ),
        (
            "https://www.youtube.com/watch?v=IvaxAtX4abc and the description is : Template 01 - Cut 0.25 to 1.00",
            {"url": "https://www.youtube.com/watch?v=IvaxAtX4abc", "start": 25, "end": 60, "template": "01"},
        ),
        (
            "https://youtu.be/xZDk-vyZm3w - Cut 0:25-1:00 template 01",
            {"url": "https://youtu.be/xZDk-vyZm3w", "start": 25, "end": 60, "template": "01"},
        ),
        (
            "https://www.tiktok.com/@user/video/12345 and the description is : my custom caption",
            {"url": "https://www.tiktok.com/@user/video/12345", "start": None, "end": None, "template": "01", "title_contains": "my custom caption"},
        ),
        # Template 00 — no burned card, clean vertical
        (
            "https://www.youtube.com/watch?v=IvaxAtX4abc Template 00 - Cut 0.25 to 1.00",
            {"url": "https://www.youtube.com/watch?v=IvaxAtX4abc", "start": 25, "end": 60, "template": "00", "title": "", "subtitle": ""},
        ),
        (
            "https://www.youtube.com/watch?v=IvaxAtX4abc Template 00 and the description is : hello world caption",
            {"url": "https://www.youtube.com/watch?v=IvaxAtX4abc", "start": None, "end": None, "template": "00", "title": "", "subtitle": "", "caption": "hello world caption"},
        ),
        (
            "https://www.youtube.com/watch?v=IvaxAtX4abc Template 00 --no-watermark",
            {"url": "https://www.youtube.com/watch?v=IvaxAtX4abc", "start": None, "end": None, "template": "00", "title": "", "subtitle": "", "handle": ""},
        ),
    ]
    ok = True
    for idx, (msg, expect) in enumerate(cases, 1):
        got = parse_message(msg)
        print(f"\n[{idx}] {msg[:90]}")
        print(f"  parsed url={got['url']} start={got['start']} end={got['end']} template={got['template']} title={got['title']!r}")
        for k, v in expect.items():
            if k == "title_contains":
                if v not in got["title"] and v not in got["caption"]:
                    print(f"  FAIL title/caption should contain {v!r} got title={got['title']!r} caption={got['caption']!r}")
                    ok = False
                else:
                    print(f"  check {k}={v!r} OK")
            else:
                if got.get(k) != v:
                    print(f"  FAIL {k}: expected {v!r} got {got.get(k)!r}")
                    ok = False
                else:
                    print(f"  check {k}={v!r} OK")
        # download-sections format sanity
        if got["start"] is not None and got["end"] is not None:
            sect = f"*{_fmt_secs(got['start'])}-{_fmt_secs(got['end'])}"
            print(f"  download-sections {sect}")
    # also verify download helper exists
    try:
        from core.downloader import _fmt_secs as _dfs
        assert _dfs(25) == "0:25"
        assert _dfs(1579) == "26:19"
        assert _dfs(60) == "1:00"
        print("\n_fmt_secs helper OK")
    except Exception as e:
        print(f"\n_fmt_secs check FAIL: {e}")
        ok = False
    # verify bot handlers importable
    try:
        import ui.messages as _m
        assert hasattr(_m, "start")
        print("ui.messages OK")
    except Exception as e:
        print(f"ui.messages FAIL {e}")
        ok = False
    print("\ndry-run", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# --- config check ------------------------------------------------------

def check_config_mode() -> int:
    problems = check_config()
    if problems:
        print("CONFIG PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("config OK")
    print(f"  jobs dir:     {config.jobs_dir}")
    print(f"  waterfox:     {config.waterfox_profile}")
    print(f"  opencode:     {config.opencode_server_url}")
    print(f"  bot token:    set ({len(config.bot_token)} chars)")
    return 0


# --- Telegram bot (only imported when actually running) ---------------

def _build_bot():
    # lazy imports so --dry-run / --check-config don't require Telegram token
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

    import ui.messages as msgs
    from core.downloader import download
    from core.interrupt import registry
    from core.jobs import CANCELLED, DOWNLOADED, DOWNLOADING, FAILED, MONTAGING, NEW, UPLOADING, VERIFIED, VERIFYING, DONE, JobStore, interruptible
    from core.verifier import verify_url

    store = JobStore(config.jobs_dir)

    async def _edit(msg, text, chat_id=None, bot=None):
        try:
            await msg.edit_text(text)
        except Exception:
            if chat_id and bot:
                try:
                    await bot.send_message(chat_id=chat_id, text=text)
                except Exception:
                    pass

    async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            return
        name = (update.effective_user.first_name if update.effective_user else "there")
        await update.message.reply_text(msgs.start(name))

    async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            return
        job = store.active_job()
        if not job:
            await update.message.reply_text(msgs.NOT_QUEUED_BY_YOU)
            return
        detail = job.get("state", "")
        # enrich with video path if present
        await update.message.reply_text(msgs.JOB_STATE.format(job_id=job["id"], state=job["state"], detail=detail))

    async def interrupt_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            return
        job = store.active_job()
        if not job or not interruptible(job):
            await update.message.reply_text(msgs.INTERRUPTED_NO_JOB)
            return
        cur_state = job.get("state", "")
        registry.request_interrupt(job["id"])
        try:
            store.set_state(store.load(job["id"]), CANCELLED)
        except Exception:
            pass
        await update.message.reply_text(msgs.CANCELLED.format(stage=cur_state))

    async def _pipeline(job_id: str, parsed: dict, status_msg, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        # late imports inside pipeline for thread usage
        from pathlib import Path

        job = store.load(job_id)
        url = parsed["url"]
        start = parsed["start"]
        end = parsed["end"]
        title = parsed["title"]
        subtitle = parsed["subtitle"]
        caption = parsed["caption"]
        template = parsed["template"]
        handle = parsed.get("handle", "@mventor")
        platform = job.get("platform", "") or JobStore.detect_platform(url) or ""
        bot = context.bot

        async def edit(text: str):
            await _edit(status_msg, text, chat_id, bot)

        # Stage: verifying (message already sent as VERIFYING)
        try:
            store.set_state(job, VERIFYING)
        except Exception:
            pass
        if registry.is_interrupted(job_id):
            await edit(msgs.CANCELLED.format(stage=VERIFYING))
            try:
                store.set_state(store.load(job_id), CANCELLED)
            except Exception:
                pass
            return

        try:
            v = await asyncio.to_thread(verify_url, url, platform, job_id)
        except Exception as e:
            v = {"ok": False, "error": str(e), "title": None, "duration": None}
        if registry.is_interrupted(job_id):
            await edit(msgs.CANCELLED.format(stage=VERIFYING))
            try:
                store.set_state(store.load(job_id), CANCELLED)
            except Exception:
                pass
            return
        if not v.get("ok"):
            await edit(msgs.VERIFY_FAILED.format(reason=v.get("error", "unknown")))
            try:
                store.set_state(store.load(job_id), FAILED)
                j = store.load(job_id)
                store.update(j, result={"error": v.get("error")})
            except Exception:
                pass
            registry.clear(job_id)
            return

        # verified ok
        dur = v.get("duration")
        dur_str = f"{int(dur)}s" if isinstance(dur, (int, float)) and dur else "?"
        # keep title from verifier if captioned? prefer verifier title for display
        vtitle = v.get("title") or title or "video"
        try:
            j = store.load(job_id)
            store.update(j, result={"title": vtitle, "duration": dur, "probe": v.get("probe")})
            store.set_state(j, VERIFIED)
        except Exception:
            pass
        await edit(msgs.VERIFIED_OK.format(title=vtitle, duration=dur_str, via=""))

        if registry.is_interrupted(job_id):
            await edit(msgs.CANCELLED.format(stage=VERIFIED))
            try:
                store.set_state(store.load(job_id), CANCELLED)
            except Exception:
                pass
            return

        # downloading
        if start is not None and end is not None:
            dl_text = f"⬇️ Downloading... Cut {_fmt_secs(start)}-{_fmt_secs(end)}"
        elif start is not None:
            dl_text = f"⬇️ Downloading... Cut {_fmt_secs(start)}-inf"
        else:
            dl_text = msgs.DOWNLOADING
        await edit(dl_text)
        try:
            store.set_state(store.load(job_id), DOWNLOADING)
        except Exception:
            pass
        output_dir = config.jobs_dir / "media"
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            d = await asyncio.to_thread(download, url, output_dir, job_id, platform, start, end)
        except Exception as e:
            d = {"ok": False, "error": str(e), "video_path": None}
        if registry.is_interrupted(job_id):
            await edit(msgs.CANCELLED.format(stage=DOWNLOADING))
            try:
                store.set_state(store.load(job_id), CANCELLED)
            except Exception:
                pass
            return
        if not d.get("ok"):
            await edit(msgs.DOWNLOAD_FAILED.format(reason=d.get("error", "unknown")))
            try:
                store.set_state(store.load(job_id), FAILED)
            except Exception:
                pass
            registry.clear(job_id)
            return
        video_path = d.get("video_path")
        streams = d.get("streams", {}) or {}
        try:
            j = store.load(job_id)
            store.update(j, video_path=str(video_path), audio_ok=streams.get("audio_ok"))
            # downloaded ok message
            sound = msgs.SOUND_OK if streams.get("audio_ok") else msgs.SOUND_MISSING
            dur2 = streams.get("duration") or dur or 0
            dur2_str = f"{dur2:.1f}s" if dur2 else dur_str
            await edit(msgs.DOWNLOADED_OK.format(sound=sound, duration=dur2_str))
            store.set_state(j, DOWNLOADED)
        except Exception:
            pass

        if not registry.should_proceed(job_id):
            await edit(msgs.CANCELLED.format(stage=DOWNLOADED))
            try:
                store.set_state(store.load(job_id), CANCELLED)
            except Exception:
                pass
            return

        # montaging
        montage_text = f"🎬 Montaging Template {template} (9:16)..."
        await edit(montage_text)
        try:
            store.set_state(store.load(job_id), MONTAGING)
        except Exception:
            pass
        out_path = output_dir / f"{job_id}_tiktok.mp4"
        try:
            from scripts.tiktok_vertical_fast import vertical_fast

            await asyncio.to_thread(vertical_fast, Path(video_path), out_path, title, subtitle, "card", "#EAB308", handle)
            ok = out_path.exists() and out_path.stat().st_size > 0
            err = None if ok else "render produced no file"
        except Exception as e:
            ok = False
            err = str(e)
        if registry.is_interrupted(job_id):
            await edit(msgs.CANCELLED.format(stage=MONTAGING))
            try:
                store.set_state(store.load(job_id), CANCELLED)
            except Exception:
                pass
            return
        if not ok:
            await edit(msgs.ERROR_GENERIC.format(reason=f"montage failed: {err}"))
            try:
                store.set_state(store.load(job_id), FAILED)
            except Exception:
                pass
            registry.clear(job_id)
            return
        try:
            j = store.load(job_id)
            store.update(j, result={"tiktok_path": str(out_path)})
        except Exception:
            pass

        if not registry.should_proceed(job_id):
            await edit(msgs.CANCELLED.format(stage=MONTAGING))
            try:
                store.set_state(store.load(job_id), CANCELLED)
            except Exception:
                pass
            return

        # uploading
        await edit(msgs.UPLOADING)
        try:
            store.set_state(store.load(job_id), UPLOADING)
        except Exception:
            pass
        # Template 00: caption is TikTok post description (not burned); template 01: burned card + caption
        if template == "00":
            desc = caption  # may be "" — clean video, post desc from Description: only
        else:
            desc = caption or f"{title} - {subtitle}"
        # publisher will add hashtags if missing
        try:
            from scripts.publish_template01 import upload_tiktok

            res = await asyncio.to_thread(upload_tiktok, out_path, desc, False)
        except Exception as e:
            res = {"ok": False, "error": str(e), "url": None}
        if registry.is_interrupted(job_id):
            await edit(msgs.CANCELLED.format(stage=UPLOADING))
            try:
                store.set_state(store.load(job_id), CANCELLED)
            except Exception:
                pass
            return
        if not res.get("ok"):
            await edit(msgs.ERROR_GENERIC.format(reason=f"upload failed: {res.get('error','unknown')}"))
            try:
                store.set_state(store.load(job_id), FAILED)
            except Exception:
                pass
            registry.clear(job_id)
            return
        tiktok_url = res.get("url") or "https://www.tiktok.com/@videosforall19"
        await edit(msgs.POSTED.format(link=tiktok_url))
        # also send video as document
        try:
            with open(out_path, "rb") as f:
                await bot.send_document(chat_id=chat_id, document=f, filename=out_path.name, caption=f"✅ Posted — {tiktok_url}")
        except Exception as e:
            try:
                await bot.send_message(chat_id=chat_id, text=f"⚠️ video document send failed: {e}\n{tiktok_url}")
            except Exception:
                pass
        try:
            store.set_state(store.load(job_id), DONE)
            j = store.load(job_id)
            store.update(j, result={"tiktok_url": tiktok_url, "tiktok_path": str(out_path)})
        except Exception:
            pass
        registry.clear(job_id)

    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            return
        text = update.message.text.strip()
        # ignore empty
        if not text:
            return
        parsed = parse_message(text)
        if not parsed["url"]:
            await update.message.reply_text(msgs.UNSUPPORTED_URL)
            return
        # create job
        try:
            job = store.create(parsed["url"], prompt=parsed["caption"], template=parsed["template"])
            # stash time cut / titles for status visibility
            try:
                store.update(job, start=parsed["start"], end=parsed["end"], title=parsed["title"], subtitle=parsed["subtitle"], caption=parsed["caption"])
            except Exception:
                pass
        except Exception as e:
            await update.message.reply_text(msgs.ERROR_GENERIC.format(reason=str(e)))
            return
        # initial progress message (will be edited)
        status_msg = await update.message.reply_text(msgs.VERIFYING)
        # launch pipeline without blocking poll loop
        asyncio.create_task(_pipeline(job["id"], parsed, status_msg, update.effective_chat.id, context))

    # build application
    app = Application.builder().token(config.bot_token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("interrupt", interrupt_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app


def main() -> int:
    if "--check-config" in sys.argv:
        return check_config_mode()
    if "--dry-run" in sys.argv:
        return dry_run_mode()

    problems = check_config()
    if problems:
        for p in problems:
            print(f"CONFIG: {p}")
        print("Fix .env before starting the bot.")
        return 1
    if not config.bot_token:
        print("BOT_TOKEN not set")
        return 1

    # wire but do not auto-start in CLI test — only when explicitly run without flags
    # To start polling, user runs `python bot.py` in their own terminal (per safety rules)
    # Here we provide the polling entry point but caller must invoke it manually.
    # For this wiring task we do NOT start polling automatically in automated checks;
    # the user will run it in their terminal window.
    # However if this is invoked as `python bot.py` without flags in a terminal, we do start.
    print("Starting bot polling...")
    try:
        app = _build_bot()
        app.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        print("bot stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
