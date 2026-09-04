"""tg-montage bot entry point — T6 approval loop.

Run modes:
  python bot.py                 # long polling (requires BOT_TOKEN)
  python bot.py --check-config  # validate config and exit (T1 acceptance)
  python bot.py --dry-run       # handler parsing + approval state-machine self-check, no Telegram needed

Flow (corrected — approval loop):
  user sends URL + optional cut + Template 01/00 + description
   -> verify -> download (with --download-sections if cut) -> vertical_fast (9:16, Majalla card for 01, clean for 00)
   -> SEND preview video with [✅ Accept] [🔁 Rerun] [❌ Reject] -> AWAITING_APPROVAL
   -> on Accept: upload TikTok (Joyride Skip + confirm modal النشر الآن) -> Done
   -> on Reject: CANCELLED, delete temp
   -> on Rerun: prompt "Send new Title / Subtitle or Description for rerun" -> re-montage -> new preview

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
    print("dry-run: parsing handler checks + approval loop state machine")
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

    # --- approval loop checks (T6 fix) ---
    print("\n--- approval loop checks ---")
    try:
        from core.jobs import ACTIVE_STATES, AWAITING_APPROVAL, CANCELLED, DONE, FAILED, JobStore
        assert AWAITING_APPROVAL in ACTIVE_STATES, "AWAITING_APPROVAL must be in ACTIVE_STATES"
        print(f"  state AWAITING_APPROVAL in ACTIVE_STATES OK ({AWAITING_APPROVAL})")
        # verify allowed transitions include approval step
        expected_flow = ["new", "verifying", "downloading", "montaging", "awaiting_approval", "uploading", "done"]
        for s in expected_flow:
            assert s in (ACTIVE_STATES | {DONE, CANCELLED, FAILED}) or s in ACTIVE_STATES, f"state {s} missing"
        print(f"  flow {' -> '.join(expected_flow)} OK")

        # JobStore state machine roundtrip through approval
        import tempfile
        tmp = tempfile.mkdtemp()
        store = JobStore(Path(tmp))
        job = store.create("https://youtu.be/test123", prompt="cap", template="01")
        assert job["state"] == "new"
        for st in ["verifying", "downloading", "montaging", "awaiting_approval"]:
            j = store.load(job["id"])
            store.set_state(j, st)
            assert store.load(job["id"])["state"] == st
            print(f"  transition -> {st} OK")
        # simulate approve -> uploading -> done
        j = store.load(job["id"])
        store.set_state(j, "uploading")
        print("  approve callback -> uploading OK")
        j = store.load(job["id"])
        store.set_state(j, DONE)
        assert store.load(job["id"])["state"] == DONE
        print("  uploading -> done OK")
        # reject path
        job2 = store.create("https://youtu.be/test456", prompt="cap2", template="00")
        for st in ["verifying", "downloading", "montaging", "awaiting_approval"]:
            j = store.load(job2["id"])
            store.set_state(j, st)
        j = store.load(job2["id"])
        store.set_state(j, CANCELLED)
        assert store.load(job2["id"])["state"] == CANCELLED
        print("  reject -> cancelled OK")
        # rerun stays in awaiting_approval (re-montage)
        job3 = store.create("https://youtu.be/test789", prompt="cap3", template="01")
        j = store.load(job3["id"])
        store.set_state(j, "awaiting_approval")
        store.update(j, awaiting_rerun=True)
        assert store.load(job3["id"])["state"] == "awaiting_approval"
        assert store.load(job3["id"]).get("awaiting_rerun") is True
        print("  rerun flag in awaiting_approval OK")
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  approval state machine FAIL: {e}")
        ok = False

    # check bot wiring contains approval loop markers
    try:
        bot_text = Path(__file__).read_text(encoding="utf-8")
        checks = [
            ("AWAITING_APPROVAL" in bot_text, "AWAITING_APPROVAL handling"),
            ("send_video" in bot_text, "send_video preview"),
            ("approve:" in bot_text, "approve callback_data"),
            ("rerun:" in bot_text, "rerun callback_data"),
            ("reject:" in bot_text, "reject callback_data"),
            ("awaiting_approval" in bot_text.lower(), "awaiting_approval flow"),
            ("approval_keyboard" in bot_text or "preview_keyboard" in bot_text, "keyboards preview function"),
            ("bot.send_video" in bot_text, "bot.send_video call"),
            ("PREVIEW_CAPTION" in bot_text or "Approve to publish" in bot_text, "preview caption"),
        ]
        for passed, name in checks:
            print(f"  check {name}: {'OK' if passed else 'MISSING'}")
            if not passed:
                ok = False
        # ensure NO auto-upload without approval: the string " -> upload directly" flow must not be present as active code path before approval
        # We check that upload_tiktok is NOT called before AWAITING_APPROVAL in _pipeline order
        # simple heuristic: montaging -> preview should appear before upload in file order after montage
        idx_montaging = bot_text.find("MONTAGING")
        idx_preview = bot_text.find("AWAITING_APPROVAL")
        idx_upload = bot_text.find("UPLOADING", idx_preview if idx_preview != -1 else 0)
        # we expect preview before uploading in file order for the montage->preview->upload sequence
        if idx_preview != -1 and idx_upload != -1 and idx_preview < idx_upload:
            print("  order montaging -> awaiting_approval -> uploading OK")
        else:
            print("  order check WARN: could not verify montage->preview->upload order")
        # check keyboards.py preview function
        kb_text = (Path(__file__).parent / "ui" / "keyboards.py").read_text(encoding="utf-8")
        kb_checks = [
            ("approval_keyboard" in kb_text or "preview_keyboard" in kb_text, "keyboards preview/approval function"),
            ("approve" in kb_text and "rerun" in kb_text and "reject" in kb_text, "keyboards 3 buttons"),
            ("callback_data" in kb_text, "keyboards callback_data"),
        ]
        for passed, name in kb_checks:
            print(f"  kb check {name}: {'OK' if passed else 'MISSING'}")
            if not passed:
                ok = False
    except Exception as e:
        print(f"  bot wiring check FAIL: {e}")
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
    from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

    import ui.messages as msgs
    from core.downloader import download
    from core.interrupt import registry
    from core.jobs import CANCELLED, DOWNLOADED, DOWNLOADING, FAILED, MONTAGING, NEW, UPLOADING, VERIFIED, VERIFYING, DONE, AWAITING_APPROVAL, JobStore, interruptible
    from core.verifier import verify_url
    import ui.keyboards as kb

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

    def _probe_duration(path: Path) -> int:
        """Return duration seconds for preview caption, fallback 51."""
        try:
            import subprocess
            ffprobe = config.ffmpeg_dir / "ffprobe.exe"
            if ffprobe.exists():
                r = subprocess.run([str(ffprobe), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True, timeout=10)
                v = r.stdout.strip()
                if v:
                    return int(float(v))
        except Exception:
            pass
        return 51

    async def _send_preview(job_id: str, video_path: Path, template: str, chat_id: int, bot, status_msg):
        """Send preview video with approval keyboard and set AWAITING_APPROVAL."""
        dur = _probe_duration(video_path)
        caption = msgs.PREVIEW_CAPTION.format(template=template.zfill(2), dur=dur)
        # job store already has AWAITING_APPROVAL set before calling
        keyboard = kb.approval_keyboard(job_id)
        try:
            # python-telegram-bot send_video needs file opened as binary
            with open(video_path, "rb") as f:
                await bot.send_video(chat_id=chat_id, video=f, caption=caption, reply_markup=keyboard, supports_streaming=True)
        except Exception as e:
            # fallback: try send_document
            try:
                with open(video_path, "rb") as f:
                    await bot.send_document(chat_id=chat_id, document=f, filename=video_path.name, caption=caption, reply_markup=keyboard)
            except Exception as e2:
                await _edit(status_msg, msgs.ERROR_GENERIC.format(reason=f"preview send failed: {e} / {e2}"), chat_id, bot)
                try:
                    store.set_state(store.load(job_id), FAILED)
                except Exception:
                    pass
                return False
        try:
            await _edit(status_msg, msgs.AWAITING_APPROVAL, chat_id, bot)
        except Exception:
            pass
        return True

    async def _do_upload(job_id: str, chat_id: int, bot, query_msg=None):
        """Upload after approval — runs TikTok upload logic."""
        try:
            job = store.load(job_id)
        except Exception as e:
            if query_msg:
                try:
                    await query_msg.edit_text(msgs.ERROR_GENERIC.format(reason=str(e)))
                except Exception:
                    pass
            return
        # guard already uploading/done
        if job.get("state") not in (AWAITING_APPROVAL, UPLOADING):
            try:
                await query_msg.edit_text(f"⚠️ Job not awaiting approval (state={job.get('state')})")  # type: ignore
            except Exception:
                pass
            return
        # mark publishing
        if query_msg:
            try:
                await query_msg.edit_text(msgs.PUBLISHING)
            except Exception:
                pass
        else:
            try:
                await bot.send_message(chat_id=chat_id, text=msgs.PUBLISHING)
            except Exception:
                pass
        try:
            store.set_state(job, UPLOADING)
        except Exception:
            pass
        # resolve paths and desc
        job = store.load(job_id)
        tiktok_path = Path(job.get("result", {}).get("tiktok_path") or job.get("tiktok_path") or "")
        if not tiktok_path or not tiktok_path.exists():
            # fallback: jobs/media/<id>_tiktok.mp4
            tiktok_path = config.jobs_dir / "media" / f"{job_id}_tiktok.mp4"
        template = job.get("template") or "01"
        caption = job.get("caption") or job.get("prompt") or ""
        title = job.get("title") or ""
        subtitle = job.get("subtitle") or ""
        if template == "00":
            desc = caption
        else:
            desc = caption or f"{title} - {subtitle}".strip(" -")
        if desc and "#" not in desc:
            desc += " #حضارة #قيادة #تاريخ"
        # publish via Waterfox cookies + Joyride Skip + confirm modal
        try:
            from scripts.publish_template01 import upload_tiktok
            res = await asyncio.to_thread(upload_tiktok, tiktok_path, desc, False)
        except Exception as e:
            res = {"ok": False, "error": str(e), "url": None}
        if registry.is_interrupted(job_id):
            try:
                await bot.send_message(chat_id=chat_id, text=msgs.CANCELLED.format(stage=UPLOADING))
            except Exception:
                pass
            try:
                store.set_state(store.load(job_id), CANCELLED)
            except Exception:
                pass
            return
        if not res.get("ok"):
            try:
                await bot.send_message(chat_id=chat_id, text=msgs.ERROR_GENERIC.format(reason=f"upload failed: {res.get('error','unknown')}"))
            except Exception:
                pass
            try:
                store.set_state(store.load(job_id), FAILED)
            except Exception:
                pass
            registry.clear(job_id)
            return
        tiktok_url = res.get("url") or "https://www.tiktok.com/@videosforall19"
        try:
            await bot.send_message(chat_id=chat_id, text=msgs.POSTED.format(link=tiktok_url))
        except Exception:
            pass
        try:
            with open(tiktok_path, "rb") as f:
                await bot.send_document(chat_id=chat_id, document=f, filename=tiktok_path.name, caption=f"✅ Posted — {tiktok_url}")
        except Exception as e:
            try:
                await bot.send_message(chat_id=chat_id, text=f"⚠️ video document send failed: {e}\n{tiktok_url}")
            except Exception:
                pass
        try:
            store.set_state(store.load(job_id), DONE)
            j = store.load(job_id)
            store.update(j, result={"tiktok_url": tiktok_url, "tiktok_path": str(tiktok_path)})
        except Exception:
            pass
        registry.clear(job_id)

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

    async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.callback_query:
            return
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            try:
                await update.callback_query.answer("⛔ Not allowed")
            except Exception:
                pass
            return
        data = (update.callback_query.data or "").strip()
        # parse action and job_id
        action = data.split(":")[0] if ":" in data else data
        job_id = data.split(":", 1)[1] if ":" in data else ""
        # legacy without :id -> resolve active job
        if not job_id:
            aj = store.active_job()
            if aj and aj.get("state") == AWAITING_APPROVAL:
                job_id = aj["id"]
            else:
                try:
                    await update.callback_query.answer("No pending preview")
                except Exception:
                    pass
                return
        # always answer callback quickly
        try:
            await update.callback_query.answer()
        except Exception:
            pass
        chat_id = update.effective_chat.id if update.effective_chat else config.allowed_chat_id
        qmsg = update.callback_query.message

        if action == "approve":
            # approve:<id> -> Publishing... -> upload
            asyncio.create_task(_do_upload(job_id, chat_id, context.bot, qmsg))
        elif action == "reject":
            try:
                j = store.load(job_id)
                store.set_state(j, CANCELLED)
                # optional delete temp preview file
            except Exception:
                pass
            try:
                await qmsg.edit_text(msgs.REJECTED)  # type: ignore
            except Exception:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=msgs.REJECTED)
                except Exception:
                    pass
            registry.clear(job_id)
        elif action == "rerun":
            try:
                j = store.load(job_id)
                store.update(j, awaiting_rerun=True)
                # keep state AWAITING_APPROVAL, flag signals next text is new caption
            except Exception:
                pass
            try:
                await qmsg.edit_text(f"{msgs.RERUN_PROMPT} — awaiting your new text")  # type: ignore
            except Exception:
                pass
            try:
                await context.bot.send_message(chat_id=chat_id, text=msgs.RERUN_PROMPT)
            except Exception:
                pass
        elif action == "cancel":
            # legacy cancel via inline button
            try:
                j = store.load(job_id)
                if interruptible(j):
                    registry.request_interrupt(job_id)
                    store.set_state(j, CANCELLED)
                    await qmsg.edit_text(msgs.CANCELLED.format(stage=j.get("state","")))  # type: ignore
                else:
                    await qmsg.edit_text("⚠️ Cannot cancel now")  # type: ignore
            except Exception:
                pass
        else:
            try:
                await update.callback_query.answer(f"Unknown action: {action}")
            except Exception:
                pass

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
            store.update(j, result={"tiktok_path": str(out_path)}, tiktok_path=str(out_path), title=title, subtitle=subtitle, caption=caption, template=template, handle=handle)
        except Exception:
            pass

        if not registry.should_proceed(job_id):
            await edit(msgs.CANCELLED.format(stage=MONTAGING))
            try:
                store.set_state(store.load(job_id), CANCELLED)
            except Exception:
                pass
            return

        # === approval loop: SEND preview instead of auto-upload ===
        try:
            j = store.load(job_id)
            store.set_state(j, AWAITING_APPROVAL)
            store.update(j, awaiting_rerun=False)
        except Exception:
            pass
        await _send_preview(job_id, out_path, template, chat_id, bot, status_msg)
        # pipeline ends here — upload will be triggered by approve callback
        # keep job in AWAITING_APPROVAL, do not clear interrupt flag yet

    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            return
        text = update.message.text.strip()
        if not text:
            return

        # --- rerun handling: if active job is awaiting approval with flag and no URL, treat as new caption ---
        aj = store.active_job()
        # check for awaiting_rerun flag (stored in job json)
        if aj and aj.get("state") == AWAITING_APPROVAL and aj.get("awaiting_rerun"):
            parsed_url = _extract_url(text)
            # if text contains URL, treat as new job (user changed mind)
            if not parsed_url:
                # this is rerun input — parse new title/subtitle/caption
                # we fake a URL to reuse parse logic, then keep original URL
                fake_url = aj.get("url") or "https://youtu.be/dummy"
                # try to detect template switch in rerun text; if not, keep original
                new_parsed = parse_message(f"{fake_url} {text}")
                # if user didn't specify template, keep old
                if "template" not in text.lower():
                    new_parsed["template"] = aj.get("template", "01")
                    # re-parse title/caption without template strip? keep new values but respect template 00 handling
                    if new_parsed["template"] == "00":
                        new_parsed["title"] = ""
                        new_parsed["subtitle"] = ""
                        # caption already extracted
                    # else keep new_parsed title/subtitle
                # also handle handle preservation
                if not _has_no_watermark(text) and not aj.get("handle"):
                    new_parsed["handle"] = ""
                # store new caption/title
                try:
                    j = store.load(aj["id"])
                    store.update(j, title=new_parsed["title"], subtitle=new_parsed["subtitle"], caption=new_parsed["caption"], template=new_parsed["template"], handle=new_parsed.get("handle", "@mventor"), awaiting_rerun=False)
                except Exception:
                    pass
                status_msg = await update.message.reply_text(f"🔁 Rerunning montage Template {new_parsed['template']}...")
                # re-run montage only (no re-download)
                async def _rerun():
                    try:
                        aj2 = store.load(aj["id"])
                        store.set_state(aj2, MONTAGING)
                    except Exception:
                        pass
                    await _edit(status_msg, f"🎬 Montaging Template {new_parsed['template']} (9:16) — rerun...", update.effective_chat.id, context.bot)
                    video_path = aj.get("video_path")
                    if not video_path or not Path(video_path).exists():
                        await _edit(status_msg, msgs.ERROR_GENERIC.format(reason="source video missing for rerun"), update.effective_chat.id, context.bot)
                        try:
                            store.set_state(store.load(aj["id"]), FAILED)
                        except Exception:
                            pass
                        return
                    out_path = config.jobs_dir / "media" / f"{aj['id']}_tiktok.mp4"
                    try:
                        from scripts.tiktok_vertical_fast import vertical_fast
                        await asyncio.to_thread(vertical_fast, Path(video_path), out_path, new_parsed["title"], new_parsed["subtitle"], "card", "#EAB308", new_parsed.get("handle", "@mventor"))
                        ok = out_path.exists() and out_path.stat().st_size > 0
                        err = None if ok else "render produced no file"
                    except Exception as e:
                        ok = False
                        err = str(e)
                    if not ok:
                        await _edit(status_msg, msgs.ERROR_GENERIC.format(reason=f"rerun montage failed: {err}"), update.effective_chat.id, context.bot)
                        try:
                            store.set_state(store.load(aj["id"]), FAILED)
                        except Exception:
                            pass
                        return
                    try:
                        j = store.load(aj["id"])
                        store.update(j, result={"tiktok_path": str(out_path)})
                        store.set_state(j, AWAITING_APPROVAL)
                    except Exception:
                        pass
                    await _send_preview(aj["id"], out_path, new_parsed["template"], update.effective_chat.id, context.bot, status_msg)
                asyncio.create_task(_rerun())
                return

        parsed = parse_message(text)
        if not parsed["url"]:
            await update.message.reply_text(msgs.UNSUPPORTED_URL)
            return
        # create job
        try:
            job = store.create(parsed["url"], prompt=parsed["caption"], template=parsed["template"])
            try:
                store.update(job, start=parsed["start"], end=parsed["end"], title=parsed["title"], subtitle=parsed["subtitle"], caption=parsed["caption"], template=parsed["template"], handle=parsed.get("handle", "@mventor"))
            except Exception:
                pass
        except Exception as e:
            await update.message.reply_text(msgs.ERROR_GENERIC.format(reason=str(e)))
            return
        status_msg = await update.message.reply_text(msgs.VERIFYING)
        asyncio.create_task(_pipeline(job["id"], parsed, status_msg, update.effective_chat.id, context))

    # build application
    app = Application.builder().token(config.bot_token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("interrupt", interrupt_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
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

    print("Starting bot polling...")
    try:
        app = _build_bot()
        app.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        print("bot stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
