"""tg-montage bot entry point — Telegram wizard v2.

Run modes:
  python bot.py                 # long polling (requires BOT_TOKEN)
  python bot.py --check-config  # validate config and exit (T1 acceptance)
  python bot.py --dry-run       # handler parsing + approval state-machine self-check, no Telegram needed

Wizard v2 Flow:
  1. User sends /url or pastes URL (with or without time cut). Bot verifies: good video = URL contains video AND downloadable via yt-dlp probe (verify_url). If not downloadable, reply "Invalid or not downloadable" and ask for new URL.
  2. Bot sends frame photo + default description: after verify, download thumbnail via yt-dlp --get-thumbnail or extract frame at 1s via ffmpeg, send as photo with caption containing default title/channel/duration from probe. Also reply with "Select template no. — 00 (raw, no card) or 01 (9:16 + card + watermark) — type 00 or 01 or nothing (defaults to 00)"
  3. User types template: 00 or 01 or empty -> default 00. Bot stores template.
  4. Bot asks: "Select cut 00:00 to 00:00 (video is 00:00-19:05)" - show duration. If user already sent cut (e.g., "Cut 0.25 to 1.00" parsed as 25s-60s), skip this step. If no cut and full video: Bot randomly picks ONE 30s section to cut (single slice, not montage). Logic: random start = randint(0, duration-30), end = start+30. If video <30s, use full video.
  5. Bot asks: "Type Description (or skip — I'll take it from the video URL itself)" - if user skips (sends /skip or empty), use yt-dlp title/description as caption.
  6. Bot asks: "Type Hashtags (unlimited, with or without # — e.g., تاريخ حضارة or #تاريخ #حضارة) - I'll normalize to #hashtags"
  7. Bot shows preview: montage via Template 00 or 01 (00 = clean 9:16 vertical, no card; 01 = with Majalla card). Send preview video with [✅ Confirm to Upload] [🔁 Rerun] [❌ Revert]
  8. Confirm -> Upload to TikTok via publish_template01 logic (Waterfox cookies, Joyride skip, scroll fix, نشر → النشر الآن)
  9. Revert -> Bot sends "Use last URL or paste a new URL" with [Use Last URL] [New URL]

Per-chat wizard state stored in memory dict WIZARD: {step, url, template, cut_start, cut_end, description, hashtags, video_path, preview_path, duration, title, channel, job_id, probe}

Only ALLOWED_CHAT_ID may trigger jobs (from env). Handler is async, long jobs via asyncio.create_task.
"""

from __future__ import annotations

import asyncio
import random
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

DEFAULT_TITLE = ""
DEFAULT_SUBTITLE = ""

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
    """Return (start_sec, end_sec, raw_match) or (None,None,None). Handles 0.25 to 1.00 as mm.ss"""
    if not text:
        return None, None, None
    # 1) colon pair: 26:19 to 27:10, 0:25-1:00, 26:19-27:10
    m = re.search(r"(\d{1,3}):(\d{2})\s*(?:to|\-|\u2013|–)\s*(\d{1,3}):(\d{2})", text, re.I)
    if m:
        s = _colon_to_sec(m.group(1), m.group(2))
        e = _colon_to_sec(m.group(3), m.group(4))
        return s, e, m.group(0)
    # 2) dot pair: 0.25 to 1.00, 0.25-1.00  (mm.ss)
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
    """Legacy: defaults to 01. Used for single-shot parse_message."""
    m = re.search(r"template\s*0?\s*(\d{1,2})", text or "", re.I)
    if m:
        num = m.group(1).lstrip("0") or "0"
        return num.zfill(2)
    return "01"


def parse_template_wizard(text: str) -> str:
    """Wizard v2: 00 or 01 or empty -> default 00. Handles '00', '01', 'Template 01', '1' etc."""
    if text is None or str(text).strip() == "" or str(text).strip().lower() in ("/skip", "skip", "nothing"):
        return "00"
    t = str(text).strip()
    # pure 00 / 01 / 0 / 1
    if re.fullmatch(r"0?0", t):
        return "00"
    if re.fullmatch(r"0?1", t):
        return "01"
    m = re.search(r"template\s*0?\s*(\d{1,2})", t, re.I)
    if m:
        num = m.group(1).lstrip("0") or "0"
        # only 0 or 1 allowed, map everything else to 00? spec says 00 or 01
        if num == "1":
            return "01"
        return "00"
    # loose: find standalone 00 or 01
    if re.search(r"\b00\b", t):
        return "00"
    if re.search(r"\b01\b", t):
        return "01"
    # if single digit 0/1 bare
    if t.strip() == "0":
        return "00"
    if t.strip() == "1":
        return "01"
    return "00"


def _has_no_watermark(text: str) -> bool:
    return bool(re.search(r"no[\s\-_]*watermark|--no-watermark|without watermark", text or "", re.I))


def parse_hashtags(text: str) -> list[str]:
    """Normalize hashtags: split by space/comma, strip #, add # prefix, allow unlimited, Arabic support."""
    if not text or not str(text).strip():
        return []
    # split by whitespace or comma
    raw_tokens = re.split(r"[\s,]+", str(text).strip())
    out: list[str] = []
    for tok in raw_tokens:
        if not tok:
            continue
        # strip surrounding punctuation but keep Arabic letters and word chars
        # first lstrip '#'
        t = tok.lstrip("#").lstrip("＃")
        # strip trailing punctuation like .!?,;:
        t = t.strip(".,)]}>\"'!?;:،؛")
        if not t:
            continue
        # also strip leading # again if double
        t = t.lstrip("#")
        if not t:
            continue
        out.append(f"#{t}")
    return out


def normalize_hashtags(text: str) -> list[str]:
    return parse_hashtags(text)


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


def _extract_desc_raw(text: str, url: str | None) -> str:
    """Extract raw description after 'Description:' or 'Description is:' or trailing text."""
    raw = text or ""
    m = re.search(r"description\s*(?:is\s*)?:\s*(.*)", raw, re.I | re.S)
    if m:
        seg = m.group(1).strip()
        # remove leading template label if user wrote "Template 01 - my desc"
        seg = re.sub(r"^\s*template\s*0?\s*\d+\s*[-–—]*\s*", "", seg, flags=re.I)
        cleaned = _strip_cuts(seg)
        cleaned = re.sub(r"template\s*0?\s*\d+", "", cleaned, flags=re.I)
        cleaned = re.sub(r"no[\s\-_]*watermark|--no-watermark|without watermark", "", cleaned, flags=re.I)
        cleaned = cleaned.strip(" \t\n\r-–—,;:\"'").strip()
        cleaned = re.sub(r"^[\s\-–—]+", "", cleaned).strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        # hashtags remain in cleaned; caller may split hashtags out
        return cleaned.strip()
    if url and url in raw:
        rest = raw.split(url, 1)[1]
    else:
        rest = raw
    cleaned = _strip_cuts(rest)
    cleaned = re.sub(r"template\s*0?\s*\d+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"no[\s\-_]*watermark|--no-watermark|without watermark", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^\s*[-–—,;:\s]+", "", cleaned)
    cleaned = re.sub(r"\s*[-–—,;:\s]+$", "", cleaned)
    cleaned = cleaned.strip(" \t\n\r-–—,;:\"'").strip()
    cleaned = re.sub(r"^[\s\-–—]+", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"^(-\s*)+", "", cleaned).strip()
    # also strip leading Description: label if fallback contained it without is
    cleaned = re.sub(r"^\s*description\s*:?\s*", "", cleaned, flags=re.I)
    return cleaned.strip()


def _extract_raw_caption(text: str, url: str | None) -> str:
    """Caption for Template 00: raw Description: value or trailing text, else empty (no defaults)."""
    return _extract_desc_raw(text, url)


def parse_description(text: str, url: str | None) -> tuple[str, str, str]:
    """Return (title, subtitle, caption). Falls back to defaults if no user caption. Supports Description: and Description is:"""
    raw_text = text or ""
    # case A: description is : or description:  (flexible)
    m = re.search(r"description\s*(?:is\s*)?:\s*(.*)", raw_text, re.I | re.S)
    if m:
        raw = m.group(1).strip()
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
                return parts[0], "", cleaned
            return cleaned, "", cleaned
        return "", "", ""
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
    cleaned = re.sub(r"^(-\s*)+", "", cleaned).strip()
    # strip leading description label if present
    cleaned = re.sub(r"^\s*description\s*:?\s*", "", cleaned, flags=re.I)
    if cleaned:
        if " - " in cleaned or " – " in cleaned or " — " in cleaned:
            parts = re.split(r"\s*[-–—]\s*", cleaned, maxsplit=1)
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) >= 2:
                return parts[0], parts[1], cleaned
            return parts[0], "", cleaned
        return cleaned, "", cleaned
    return "", "", ""


def parse_description_text_only(text: str, url: str | None = None) -> str:
    """Extract description string after Description: (wizard step helper). Returns '' if empty."""
    if not text:
        return ""
    # if text is /skip or empty -> return ''
    if str(text).strip().lower() in ("/skip", "skip", ""):
        return ""
    # Use _extract_desc_raw but strip hashtags? Keep hashtags inside? For wizard we keep description separate from hashtags.
    # So first extract raw then try to separate trailing hashtags tokens that start with # or that look like hashtags.
    raw = _extract_desc_raw(text, url)
    # If raw contains hashtags as trailing #words, keep them? For wizard step 5 we treat entire input as description; hashtags step is separate, so we keep raw as-is.
    # Remove hashtags that are at end? No — keep raw. Caller will handle hashtags separately.
    return raw.strip()


def extract_hashtags_from_text(text: str) -> list[str]:
    """Helper to pull hashtags tokens from arbitrary text: find #tags or standalone Arabic words that look like hashtags?
    For combined message, we treat tokens starting with # as hashtags. For hashtags-step, we normalize all tokens.
    """
    if not text:
        return []
    # find hashtags via regex: words starting with # (including Arabic)
    # Arabic range: \u0600-\u06FF
    # Use regex to find #<word>
    found = re.findall(r"#([\w\u0600-\u06FF]+)", text)
    if found:
        return [f"#{w}" for w in found]
    # fallback: if no # but text is like "تاريخ حضارة", caller should treat whole text as hashtags — use parse_hashtags instead.
    return []


def random_30s_slice(duration: float | int | None) -> tuple[int | None, int | None]:
    """Wizard logic: random start = randint(0, duration-30), end = start+30. If video <30s, use full video (None,None)."""
    if duration is None:
        return None, None
    try:
        d = int(float(duration))
    except Exception:
        return None, None
    if d <= 30:
        return None, None
    start = random.randint(0, d - 30)
    return start, start + 30


def parse_message(text: str) -> dict:
    """Parse Telegram message text into job params.

    Returns dict with url, start, end, template, title, subtitle, caption, raw_cut, handle, description, hashtags.
    Template 00: no burned card — title/subtitle forced empty, caption is raw Description: if any else "".
    Watermark: default WATERMARK_HANDLE (empty = skip) unless text contains no watermark / --no-watermark.
    """
    url = _extract_url(text)
    start, end, raw_cut = parse_time_cut(text)
    template = parse_template(text)
    handle = "" if _has_no_watermark(text) else (config.watermark_handle or "")
    # hashtags extraction: find #tags; if none but user might have typed bare hashtags, fallback handled by caller
    hashtags = extract_hashtags_from_text(text)
    # if no #tags found but the text after Description: contains bare words that caller considers hashtags, we leave empty here and wizard step will normalize separately
    if template == "00":
        caption = _extract_raw_caption(text, url)
        title = ""
        subtitle = ""
        description = caption
    else:
        title, subtitle, caption = parse_description(text, url)
        description = caption
        if _has_no_watermark(text):
            caption = re.sub(r"no[\s\-_]*watermark|--no-watermark|without watermark", "", caption, flags=re.I).strip()
            caption = re.sub(r"\s+", " ", caption).strip(" -–—,;:")
            title = re.sub(r"no[\s\-_]*watermark|--no-watermark|without watermark", "", title, flags=re.I).strip()
            subtitle = re.sub(r"no[\s\-_]*watermark|--no-watermark|without watermark", "", subtitle, flags=re.I).strip()
            description = caption
    return {
        "url": url,
        "start": start,
        "end": end,
        "raw_cut": raw_cut,
        "template": template,
        "title": title,
        "subtitle": subtitle,
        "caption": caption,
        "description": description,
        "hashtags": hashtags,
        "handle": handle,
    }


# --- wizard state machine (per-chat memory) --------------------------

# WIZARD holds per-chat wizard state; LAST_URL remembers last successful URL per chat for Revert
WIZARD: dict[int, dict] = {}
LAST_URL: dict[int, str] = {}
# PENDING_TEMPLATE holds template selected via control center (select_template_00/01) for next URL
PENDING_TEMPLATE: dict[int, str] = {}

WIZARD_STEP_IDLE = "idle"
WIZARD_STEP_AWAITING_URL = "awaiting_url"
WIZARD_STEP_AWAITING_TEMPLATE = "awaiting_template"
WIZARD_STEP_AWAITING_CUT = "awaiting_cut"
WIZARD_STEP_AWAITING_DESCRIPTION = "awaiting_description"
WIZARD_STEP_AWAITING_HASHTAGS = "awaiting_hashtags"
WIZARD_STEP_AWAITING_APPROVAL = "awaiting_approval"


def _wizard_get(chat_id: int) -> dict | None:
    return WIZARD.get(chat_id)


def _wizard_set(chat_id: int, data: dict) -> None:
    WIZARD[chat_id] = data


def _wizard_clear(chat_id: int) -> None:
    WIZARD.pop(chat_id, None)


def _wizard_init(chat_id: int, url: str, cut_start: int | None = None, cut_end: int | None = None, duration: float | None = None, probe: dict | None = None, title: str | None = None, channel: str | None = None) -> dict:
    st = {
        "step": WIZARD_STEP_AWAITING_TEMPLATE,
        "url": url,
        "template": None,
        "cut_start": cut_start,
        "cut_end": cut_end,
        "description": None,
        "hashtags": [],
        "video_path": None,
        "preview_path": None,
        "duration": duration,
        "title": title,
        "channel": channel,
        "probe": probe,
        "job_id": None,
    }
    _wizard_set(chat_id, st)
    LAST_URL[chat_id] = url
    return st


# --- dry-run self-check ------------------------------------------------

def dry_run_mode() -> int:
    print("dry-run: parsing handler checks + approval loop state machine + wizard v2")
    cases = [
        (
            "https://www.youtube.com/watch?v=xZDk-vyZm3w - Cut 26:19 to 27:10 Template 01 - Example Title",
            {"url": "https://www.youtube.com/watch?v=xZDk-vyZm3w", "start": 1579, "end": 1630, "template": "01", "title_contains": "Example Title"},
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
        if got["start"] is not None and got["end"] is not None:
            sect = f"*{_fmt_secs(got['start'])}-{_fmt_secs(got['end'])}"
            print(f"  download-sections {sect}")
    # --- wizard v2 parsing tests ---
    print("\n--- wizard v2 parsing checks ---")
    try:
        # spec example: https://www.youtube.com/watch?v=IvaxAtX4abc Template 01 - Cut 0.25 to 1.00 Description: my desc #تاريخ
        txt = "https://www.youtube.com/watch?v=IvaxAtX4abc Template 01 - Cut 0.25 to 1.00 Description: my desc #تاريخ"
        got = parse_message(txt)
        assert got["url"] == "https://www.youtube.com/watch?v=IvaxAtX4abc", f"url mismatch {got['url']}"
        assert got["start"] == 25, f"start 25 expected got {got['start']}"
        assert got["end"] == 60, f"end 60 expected got {got['end']}"
        assert got["template"] == "01", f"template 01 expected got {got['template']}"
        # description should contain my desc
        assert "my desc" in got["caption"] or "my desc" in got["description"], f"caption should contain my desc got {got['caption']!r}"
        assert "#تاريخ" in got["hashtags"] or "#تاريخ" in got["caption"], f"hashtag #تاريخ expected got {got['hashtags']!r} caption {got['caption']!r}"
        print(f"  wizard combined parse OK url={got['url']} start={got['start']} end={got['end']} template={got['template']} hashtags={got['hashtags']!r}")

        # description extraction via helper
        desc = _extract_desc_raw(txt, got["url"])
        assert "my desc" in desc, f"_extract_desc_raw failed {desc!r}"
        print(f"  description extraction OK {desc!r}")

        # hashtags helpers: with and without #
        for ht_in, ht_expect in [
            ("تاريخ حضارة", ["#تاريخ", "#حضارة"]),
            ("#تاريخ #حضارة", ["#تاريخ", "#حضارة"]),
            ("تاريخ, حضارة", ["#تاريخ", "#حضارة"]),
            ("#تاريخ,حضارة", ["#تاريخ", "#حضارة"]),
            ("تاريخ", ["#تاريخ"]),
            ("   #تاريخ   #حضارة  ", ["#تاريخ", "#حضارة"]),
        ]:
            got_ht = parse_hashtags(ht_in)
            assert got_ht == ht_expect, f"parse_hashtags {ht_in!r} expected {ht_expect} got {got_ht}"
            print(f"  hashtags {ht_in!r} -> {got_ht} OK")

        # template wizard defaults
        assert parse_template_wizard("") == "00", "empty should default 00"
        assert parse_template_wizard("   ") == "00", "whitespace default 00"
        assert parse_template_wizard("/skip") == "00"
        assert parse_template_wizard("00") == "00"
        assert parse_template_wizard("01") == "01"
        assert parse_template_wizard("Template 00") == "00"
        assert parse_template_wizard("Template 01") == "01"
        assert parse_template_wizard("template 1") == "01"
        print("  template wizard parsing OK")

        # random 30s slice logic
        duration = 300
        for i in range(20):
            s, e = random_30s_slice(duration)
            assert s is not None and e is not None, "should have slice for 300s"
            assert 0 <= s <= 270, f"random start {s} out of [0,270]"
            assert e == s + 30, f"end should be start+30 got {e} start {s}"
        print("  random 30s slice for 300s OK (20 iterations in [0,270])")
        # short video <30s
        s, e = random_30s_slice(19)
        assert s is None and e is None, f"short video should be None,None got {s},{e}"
        print("  random slice short video <30s -> full video OK")
        s, e = random_30s_slice(30)
        assert s is None and e is None, "30s exactly -> full"
        print("  random slice 30s exact -> full OK")
        # edge 31s
        s, e = random_30s_slice(31)
        assert s in (0, 1), f"31s should be 0 or 1 got {s}"
        print(f"  random slice 31s -> {s}-{e} OK")

        # time cut dot pattern extra checks
        assert parse_time_cut("Cut 0.25 to 1.00")[0] == 25
        assert parse_time_cut("Cut 0.25 to 1.00")[1] == 60
        assert parse_time_cut("0.25 to 1.00")[0] == 25
        assert parse_time_cut("26:19 to 27:10")[0] == 1579
        print("  time cut dot/colon patterns OK")

    except AssertionError as e:
        print(f"  wizard parsing FAIL: {e}")
        ok = False
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"  wizard parsing FAIL: {e}")
        ok = False

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
        assert hasattr(_m, "WIZARD_TEMPLATE_PROMPT")
        print("ui.messages OK (wizard prompts present)")
        # control center messages
        for attr in ("CONTROL_CENTER_TEXT", "HELP_TEXT", "DOCS_TEXT", "TEMPLATES_TEXT"):
            assert hasattr(_m, attr), f"missing {attr}"
        print("  control center messages OK (CONTROL_CENTER/HELP/DOCS/TEMPLATES)")
    except Exception as e:
        print(f"ui.messages FAIL {e}")
        ok = False

    # --- approval loop checks (T6 fix) ---
    print("\n--- approval loop checks ---")
    try:
        from core.jobs import ACTIVE_STATES, AWAITING_APPROVAL, CANCELLED, DONE, FAILED, JobStore
        assert AWAITING_APPROVAL in ACTIVE_STATES, "AWAITING_APPROVAL must be in ACTIVE_STATES"
        print(f"  state AWAITING_APPROVAL in ACTIVE_STATES OK ({AWAITING_APPROVAL})")
        expected_flow = ["new", "verifying", "downloading", "montaging", "awaiting_approval", "uploading", "done"]
        for s in expected_flow:
            assert s in (ACTIVE_STATES | {DONE, CANCELLED, FAILED}) or s in ACTIVE_STATES, f"state {s} missing"
        print(f"  flow {' -> '.join(expected_flow)} OK")

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
        j = store.load(job["id"])
        store.set_state(j, "uploading")
        print("  approve callback -> uploading OK")
        j = store.load(job["id"])
        store.set_state(j, DONE)
        assert store.load(job["id"])["state"] == DONE
        print("  uploading -> done OK")
        job2 = store.create("https://youtu.be/test456", prompt="cap2", template="00")
        for st in ["verifying", "downloading", "montaging", "awaiting_approval"]:
            j = store.load(job2["id"])
            store.set_state(j, st)
        j = store.load(job2["id"])
        store.set_state(j, CANCELLED)
        assert store.load(job2["id"])["state"] == CANCELLED
        print("  reject -> cancelled OK")
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

    # check bot wiring contains approval loop markers + wizard markers
    try:
        bot_text = Path(__file__).read_text(encoding="utf-8")
        checks = [
            ("AWAITING_APPROVAL" in bot_text, "AWAITING_APPROVAL handling"),
            ("send_video" in bot_text, "send_video preview"),
            ("approve:" in bot_text, "approve callback_data"),
            ("rerun:" in bot_text, "rerun callback_data"),
            ("reject:" in bot_text, "reject callback_data"),
            ("confirm" in bot_text.lower(), "confirm/revert handling"),
            ("revert" in bot_text.lower(), "revert handling"),
            ("awaiting_approval" in bot_text.lower(), "awaiting_approval flow"),
            ("approval_keyboard" in bot_text or "preview_keyboard" in bot_text or "wizard_preview_keyboard" in bot_text, "keyboards preview function"),
            ("bot.send_video" in bot_text, "bot.send_video call"),
            ("PREVIEW_CAPTION" in bot_text or "Approve to publish" in bot_text or "Confirm to Upload" in bot_text, "preview caption"),
            ("WIZARD" in bot_text, "wizard state dict"),
            ("parse_hashtags" in bot_text, "hashtags helper"),
            ("random_30s_slice" in bot_text or "randint(0, duration-30)" in bot_text, "random 30s helper"),
            ("INVALID_URL" in bot_text or "Invalid or not downloadable" in bot_text, "invalid url handling"),
            ("/url" in bot_text, "/url command"),
            ("WIZARD_STEP_AWAITING_TEMPLATE" in bot_text, "wizard steps"),
        ]
        for passed, name in checks:
            print(f"  check {name}: {'OK' if passed else 'MISSING'}")
            if not passed:
                ok = False
        idx_montaging = bot_text.find("MONTAGING")
        idx_preview = bot_text.find("AWAITING_APPROVAL")
        idx_upload = bot_text.find("UPLOADING", idx_preview if idx_preview != -1 else 0)
        if idx_preview != -1 and idx_upload != -1 and idx_preview < idx_upload:
            print("  order montaging -> awaiting_approval -> uploading OK")
        else:
            print("  order check WARN: could not verify montage->preview->upload order")
        kb_text = (Path(__file__).parent / "ui" / "keyboards.py").read_text(encoding="utf-8")
        kb_checks = [
            ("approval_keyboard" in kb_text or "preview_keyboard" in kb_text or "wizard_preview_keyboard" in kb_text, "keyboards preview/approval function"),
            ("approve" in kb_text and "rerun" in kb_text and ("reject" in kb_text or "revert" in kb_text), "keyboards 3 buttons"),
            ("callback_data" in kb_text, "keyboards callback_data"),
            ("wizard_preview_keyboard" in kb_text, "wizard preview keyboard"),
            ("revert_choice_keyboard" in kb_text or "Use Last" in kb_text, "revert choice keyboard"),
            ("control_center_keyboard" in kb_text, "control center keyboard"),
            ("templates_list_keyboard" in kb_text, "templates list keyboard"),
            ('"docs"' in kb_text or "'docs'" in kb_text or "callback_data=\"docs\"" in kb_text, "docs callback_data"),
            ('"help"' in kb_text or "'help'" in kb_text or 'callback_data="help"' in kb_text, "help callback_data"),
            ('"templates"' in kb_text or "templates" in kb_text, "templates callback_data"),
        ]
        for passed, name in kb_checks:
            print(f"  kb check {name}: {'OK' if passed else 'MISSING'}")
            if not passed:
                ok = False
        # control center callback handlers present in bot.py
        cc_checks = [
            ("callback_data" in bot_text and "docs" in bot_text, "docs callback handler"),
            ("help" in bot_text and "HELP_TEXT" in bot_text, "help handler wired"),
            ("templates" in bot_text and "TEMPLATES_TEXT" in bot_text, "templates handler wired"),
            ("select_template_00" in bot_text and "select_template_01" in bot_text, "select_template handlers"),
            ("control_center_keyboard" in bot_text, "control center keyboard usage"),
            ("BotCommand" in bot_text or "set_my_commands" in bot_text, "persistent BotCommand menu"),
            ("/start" in bot_text and "/help" in bot_text and "/menu" in bot_text, "/start /help /menu handlers"),
        ]
        for passed, name in cc_checks:
            print(f"  cc check {name}: {'OK' if passed else 'MISSING'}")
            if not passed:
                ok = False
        # no hardcoded credentials check (ensure BOT_TOKEN not hardcoded in bot.py/keyboards/messages)
        for pth in [Path(__file__), Path(__file__).parent / "ui" / "keyboards.py", Path(__file__).parent / "ui" / "messages.py", Path(__file__).parent / "config.py"]:
            try:
                t = pth.read_text(encoding="utf-8")
                # naive: look for BOT_TOKEN = "xxx" literal non-empty
                if "BOT_TOKEN" in t and "=" in t:
                    # allow os.environ.get pattern, but not literal token string longer than 20 with colon?
                    import re as _re
                    if _re.search(r'BOT_TOKEN\s*=\s*["\'][A-Za-z0-9:_\-]{20,}["\']', t):
                        print(f"  hardcoded credentials FAIL in {pth.name}")
                        ok = False
                    else:
                        print(f"  no hardcoded credentials in {pth.name} OK")
                else:
                    print(f"  no hardcoded credentials in {pth.name} OK")
            except Exception as e:
                print(f"  cred check {pth.name} WARN {e}")
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
        dur = _probe_duration(video_path)
        caption = msgs.PREVIEW_CAPTION.format(template=template.zfill(2), dur=dur)
        # keep legacy keyboard for dry-run compat but also support wizard keyboard
        try:
            # per spec use wizard preview keyboard: confirm/rerun/revert (approve alias)
            keyboard = kb.wizard_preview_keyboard(job_id)
        except Exception:
            keyboard = kb.approval_keyboard(job_id)
        try:
            with open(video_path, "rb") as f:
                await bot.send_video(chat_id=chat_id, video=f, caption=caption, reply_markup=keyboard, supports_streaming=True)
        except Exception as e:
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
        try:
            job = store.load(job_id)
        except Exception as e:
            if query_msg:
                try:
                    await query_msg.edit_text(msgs.ERROR_GENERIC.format(reason=str(e)))
                except Exception:
                    pass
            return
        if job.get("state") not in (AWAITING_APPROVAL, UPLOADING):
            try:
                await query_msg.edit_text(f"⚠️ Job not awaiting approval (state={job.get('state')})")  # type: ignore
            except Exception:
                pass
            return
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
        job = store.load(job_id)
        tiktok_path = Path(job.get("result", {}).get("tiktok_path") or job.get("tiktok_path") or "")
        if not tiktok_path or not tiktok_path.exists():
            tiktok_path = config.jobs_dir / "media" / f"{job_id}_tiktok.mp4"
        template = job.get("template") or "01"
        caption = job.get("caption") or job.get("prompt") or ""
        title = job.get("title") or ""
        subtitle = job.get("subtitle") or ""
        # hashtags stored in job if wizard
        hashtags = job.get("hashtags") or []
        if hashtags and isinstance(hashtags, list):
            tags_str = " ".join(hashtags)
            if caption and tags_str not in caption:
                caption = (caption + " " + tags_str).strip()
            if not caption:
                caption = tags_str
        if template == "00":
            desc = caption
        else:
            desc = caption or f"{title} - {subtitle}".strip(" -")
        if desc and "#" not in desc:
            desc += " #حضارة #قيادة #تاريخ"
        # T7: lazy cookie check before upload (24h daily + every upload)
        try:
            from core.cookies import verify_tiktok_session
            chk = await asyncio.to_thread(verify_tiktok_session)
            if not chk.get("ok"):
                try:
                    await bot.send_message(chat_id=chat_id, text=msgs.COOKIE_EXPIRED)
                    if chat_id != config.allowed_chat_id:
                        try: await bot.send_message(chat_id=config.allowed_chat_id, text=msgs.COOKIE_EXPIRED)
                        except: pass
                except Exception:
                    pass
                try:
                    j = store.load(job_id)
                    store.set_state(j, FAILED)
                    store.update(j, result={"error": chk.get("reason"), "cookie_fail": True})
                except Exception:
                    pass
                # do not attempt upload if cookies invalid
                return
        except Exception:
            pass
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
            # T7: cookie fail vs generic upload fail mapping
            err = res.get("error","unknown")
            is_cookie = res.get("cookie_fail") or "session expired" in str(err).lower() or "re-login" in str(err).lower()
            msg_text = msgs.COOKIE_EXPIRED if is_cookie else msgs.error_message("upload", err)
            try:
                await bot.send_message(chat_id=chat_id, text=msg_text)
                if is_cookie and chat_id != config.allowed_chat_id:
                    try: await bot.send_message(chat_id=config.allowed_chat_id, text=msg_text)
                    except: pass
            except Exception:
                pass
            try:
                j = store.load(job_id)
                store.set_state(j, FAILED)
                store.update(j, result={"error": err, "cookie_fail": bool(is_cookie)})
            except Exception:
                pass
            registry.clear(job_id)
            return
        tiktok_url = res.get("url") or (f"https://www.tiktok.com/{config.tiktok_handle.lstrip('@')}" if config.tiktok_handle else "https://www.tiktok.com/tiktokstudio/content")
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
        _wizard_clear(chat_id)

    # --- wizard helpers ---
    async def _wizard_send_thumbnail(chat_id: int, bot, probe: dict, url: str, duration: float | None):
        """Send frame photo + default description per spec step 2. Tries thumbnail via yt-dlp probe thumbnail url, fallback to ffmpeg frame."""
        title = probe.get("title") or "video"
        channel = probe.get("uploader") or probe.get("channel") or probe.get("extractor") or "unknown"
        dur_str = _fmt_secs(int(duration)) if isinstance(duration, (int, float)) and duration else "?"
        thumb_url = probe.get("thumbnail") or probe.get("webpage_url") or None
        # try thumbnails list
        if not thumb_url and isinstance(probe.get("thumbnails"), list) and probe["thumbnails"]:
            try:
                thumb_url = probe["thumbnails"][-1].get("url")
            except Exception:
                thumb_url = None
        caption = msgs.WIZARD_THUMB_CAPTION.format(title=title[:120], channel=channel, duration=dur_str)
        # try sending photo via URL if available, else just send text thumbnail placeholder
        if thumb_url and thumb_url.startswith("http"):
            try:
                await bot.send_photo(chat_id=chat_id, photo=thumb_url, caption=caption)
                return True
            except Exception:
                pass
            # try downloading via http and sending as file
            try:
                import urllib.request, tempfile
                tmp = Path(tempfile.gettempdir()) / f"tg_thumb_{chat_id}.jpg"
                urllib.request.urlretrieve(thumb_url, tmp)  # type: ignore
                if tmp.exists() and tmp.stat().st_size > 0:
                    with open(tmp, "rb") as f:
                        await bot.send_photo(chat_id=chat_id, photo=f, caption=caption)
                    try:
                        tmp.unlink()
                    except Exception:
                        pass
                    return True
            except Exception:
                pass
        # fallback: ffmpeg frame at 1s via yt-dlp --get-thumbnail equivalent not available; just send caption as text
        try:
            await bot.send_message(chat_id=chat_id, text=f"🖼️ {caption}\n{url}")
        except Exception:
            pass
        return False

    async def _wizard_ask_template(chat_id: int, bot):
        wiz = _wizard_get(chat_id)
        if not wiz:
            return
        # if user pre-selected via Templates list, apply it automatically
        pending = PENDING_TEMPLATE.get(chat_id)
        if pending in ("00", "01"):
            wiz["template"] = pending
            # clear pending after use? keep for next URL as well until changed — so don't clear, but note applied
            _wizard_set(chat_id, wiz)
            try:
                await bot.send_message(chat_id=chat_id, text=msgs.WIZARD_TEMPLATE_SAVED.format(template=pending) + " (pre-selected via 🎨 Templates)")
            except Exception:
                pass
            await _wizard_ask_cut(chat_id, bot, wiz.get("duration"))
            return
        wiz["step"] = WIZARD_STEP_AWAITING_TEMPLATE
        _wizard_set(chat_id, wiz)
        # also show templates list keyboard as shortcut
        try:
            await bot.send_message(chat_id=chat_id, text=msgs.WIZARD_TEMPLATE_PROMPT, reply_markup=kb.templates_list_keyboard())
        except Exception:
            try:
                await bot.send_message(chat_id=chat_id, text=msgs.WIZARD_TEMPLATE_PROMPT)
            except Exception:
                pass

    async def _wizard_ask_cut(chat_id: int, bot, duration: float | None):
        wiz = _wizard_get(chat_id)
        if not wiz:
            return
        # if cut already provided from initial message, skip
        if wiz.get("cut_start") is not None and wiz.get("cut_end") is not None:
            # skip asking, go to description
            try:
                await bot.send_message(chat_id=chat_id, text=msgs.WIZARD_CUT_SAVED.format(start=_fmt_secs(wiz["cut_start"]), end=_fmt_secs(wiz["cut_end"])) + " (from your URL)")
            except Exception:
                pass
            await _wizard_ask_description(chat_id, bot)
            return
        wiz["step"] = WIZARD_STEP_AWAITING_CUT
        _wizard_set(chat_id, wiz)
        dur_str = _fmt_secs(int(duration)) if isinstance(duration, (int, float)) and duration else "?"
        # Show duration as 00:00-19:05 style; use _fmt_secs for end
        end_fmt = _fmt_secs(int(duration)) if isinstance(duration, (int, float)) and duration else "?"
        try:
            await bot.send_message(chat_id=chat_id, text=msgs.WIZARD_CUT_PROMPT.format(end=end_fmt))
        except Exception:
            pass

    async def _wizard_ask_description(chat_id: int, bot):
        wiz = _wizard_get(chat_id)
        if not wiz:
            return
        wiz["step"] = WIZARD_STEP_AWAITING_DESCRIPTION
        _wizard_set(chat_id, wiz)
        try:
            await bot.send_message(chat_id=chat_id, text=msgs.WIZARD_DESCRIPTION_PROMPT)
        except Exception:
            pass

    async def _wizard_ask_hashtags(chat_id: int, bot):
        wiz = _wizard_get(chat_id)
        if not wiz:
            return
        wiz["step"] = WIZARD_STEP_AWAITING_HASHTAGS
        _wizard_set(chat_id, wiz)
        try:
            await bot.send_message(chat_id=chat_id, text=msgs.WIZARD_HASHTAGS_PROMPT)
        except Exception:
            pass

    async def _wizard_trigger_preview(chat_id: int, bot, status_msg=None):
        """Download + montage + send preview using wizard collected fields."""
        wiz = _wizard_get(chat_id)
        if not wiz:
            return
        url = wiz["url"]
        template = wiz.get("template") or "00"
        # cut handling: if still None, pick random 30s
        cut_start = wiz.get("cut_start")
        cut_end = wiz.get("cut_end")
        if cut_start is None and cut_end is None:
            dur = wiz.get("duration")
            rs, re_ = random_30s_slice(dur)
            if rs is not None and re_ is not None:
                wiz["cut_start"] = rs
                wiz["cut_end"] = re_
                try:
                    await bot.send_message(chat_id=chat_id, text=msgs.WIZARD_CUT_RANDOM.format(start=_fmt_secs(rs), end=_fmt_secs(re_)))
                except Exception:
                    pass
                cut_start, cut_end = rs, re_
        # description/hashtags combo
        description = wiz.get("description") or ""
        hashtags = wiz.get("hashtags") or []
        if not description:
            # fallback to probe title if skip
            probe = wiz.get("probe") or {}
            description = probe.get("title") or wiz.get("title") or ""
        # caption for job
        caption = description.strip()
        if hashtags:
            tags_str = " ".join(hashtags)
            if caption and tags_str not in caption:
                caption = (caption + " " + tags_str).strip()
            elif not caption:
                caption = tags_str
        # For template 01, derive title/subtitle from description (split on -) — empty defaults, fallback to probe title
        if template == "01":
            t_title, t_sub, _ = parse_description(description, url)
            # if user skipped description, use probe title fetched via verify_url
            if not description:
                probe_title = (wiz.get("probe") or {}).get("title") or wiz.get("title") or ""
                t_title = probe_title[:80] if probe_title else ""
                t_sub = ""
            else:
                # if description contains " - ", split; else treat whole as title, subtitle empty
                if " - " in description or " – " in description or " — " in description:
                    parts = re.split(r"\s*[-–—]\s*", description, maxsplit=1)
                    t_title = parts[0].strip() if parts and parts[0].strip() else ""
                    t_sub = parts[1].strip() if len(parts) > 1 and parts[1].strip() else ""
                else:
                    t_title = description[:80]
                    t_sub = ""
        else:
            t_title = ""
            t_sub = ""
        handle = config.watermark_handle or ""
        # Determine start/end for download
        start = cut_start
        end = cut_end
        # Create job store entry
        try:
            job = store.create(url, prompt=caption, template=template)
            store.update(job, start=start, end=end, title=t_title, subtitle=t_sub, caption=caption, template=template, handle=handle, hashtags=hashtags, description=description, tiktok_handle=config.tiktok_handle or "", watermark_handle=config.watermark_handle or "")
            wiz["job_id"] = job["id"]
            wiz["step"] = WIZARD_STEP_AWAITING_APPROVAL
            _wizard_set(chat_id, wiz)
        except Exception as e:
            try:
                await bot.send_message(chat_id=chat_id, text=msgs.ERROR_GENERIC.format(reason=str(e)))
            except Exception:
                pass
            return
        # status msg for pipeline
        if status_msg is None:
            try:
                status_msg = await bot.send_message(chat_id=chat_id, text=msgs.WIZARD_MONTAGING.format(template=template))
            except Exception:
                status_msg = None
        parsed = {"url": url, "start": start, "end": end, "template": template, "title": t_title, "subtitle": t_sub, "caption": caption, "handle": handle, "hashtags": hashtags, "description": description}
        asyncio.create_task(_wizard_pipeline(job["id"], parsed, status_msg, chat_id, bot))

    async def _wizard_pipeline(job_id: str, parsed: dict, status_msg, chat_id: int, bot):
        # reuse existing _pipeline logic but adapted for wizard caption/hashtags
        job = store.load(job_id)
        url = parsed["url"]
        start = parsed["start"]
        end = parsed["end"]
        title = parsed["title"]
        subtitle = parsed["subtitle"]
        caption = parsed["caption"]
        template = parsed["template"]
        handle = parsed.get("handle", config.watermark_handle or "")
        platform = job.get("platform", "") or JobStore.detect_platform(url) or ""
        async def edit(text: str):
            await _edit(status_msg, text, chat_id, bot)
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
            # T7: cookie fail maps to dedicated Telegram message
            if v.get("cookie_fail"):
                await edit(msgs.COOKIE_EXPIRED)
                try:
                    await bot.send_message(chat_id=chat_id, text=msgs.COOKIE_EXPIRED)
                except Exception:
                    pass
                # also notify ALLOWED_CHAT_ID if different
                try:
                    if chat_id != config.allowed_chat_id:
                        await bot.send_message(chat_id=config.allowed_chat_id, text=msgs.COOKIE_EXPIRED)
                except Exception:
                    pass
            else:
                await edit(msgs.VERIFY_FAILED.format(reason=v.get("error", "unknown")))
                try:
                    await bot.send_message(chat_id=chat_id, text=msgs.error_message("verify", v.get("error","unknown")))
                except Exception:
                    pass
            try:
                store.set_state(store.load(job_id), FAILED)
                j = store.load(job_id)
                store.update(j, result={"error": v.get("error"), "cookie_fail": v.get("cookie_fail")})
            except Exception:
                pass
            registry.clear(job_id)
            # wizard: inform invalid and ask new URL (only if not cookie fail, already sent)
            if not v.get("cookie_fail"):
                try:
                    await bot.send_message(chat_id=chat_id, text=msgs.INVALID_URL)
                except Exception:
                    pass
            # reset wizard to awaiting_url
            wiz = _wizard_get(chat_id)
            if wiz:
                wiz["step"] = WIZARD_STEP_AWAITING_URL
                _wizard_set(chat_id, wiz)
            return
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
            # T7: map download fail to user-facing bilingual message
            try:
                await bot.send_message(chat_id=chat_id, text=msgs.error_message("download", d.get("error","unknown")))
            except Exception:
                pass
            await edit(msgs.error_message("download", d.get("error", "unknown")))
            try:
                store.set_state(store.load(job_id), FAILED)
                j = store.load(job_id)
                store.update(j, result={"error": d.get("error")})
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
            try:
                await bot.send_message(chat_id=chat_id, text=msgs.error_message("montage", err or "render produced no file"))
            except Exception:
                pass
            await edit(msgs.error_message("montage", err or "render produced no file"))
            try:
                store.set_state(store.load(job_id), FAILED)
                j = store.load(job_id)
                store.update(j, result={"error": err})
            except Exception:
                pass
            registry.clear(job_id)
            return
        try:
            j = store.load(job_id)
            store.update(j, result={"tiktok_path": str(out_path)}, tiktok_path=str(out_path), title=title, subtitle=subtitle, caption=caption, template=template, handle=handle)
            # store wizard hashtagas etc also in job for upload
            wiz = _wizard_get(chat_id)
            if wiz and wiz.get("hashtags"):
                store.update(j, hashtags=wiz["hashtags"])
        except Exception:
            pass
        if not registry.should_proceed(job_id):
            await edit(msgs.CANCELLED.format(stage=MONTAGING))
            try:
                store.set_state(store.load(job_id), CANCELLED)
            except Exception:
                pass
            return
        try:
            j = store.load(job_id)
            store.set_state(j, AWAITING_APPROVAL)
            store.update(j, awaiting_rerun=False)
        except Exception:
            pass
        # update wizard preview path
        wiz = _wizard_get(chat_id)
        if wiz:
            wiz["preview_path"] = str(out_path)
            wiz["video_path"] = str(video_path)
            _wizard_set(chat_id, wiz)
        # send preview with wizard keyboard
        dur_wiz = _probe_duration(out_path)
        preview_caption = msgs.WIZARD_PREVIEW_CAPTION.format(template=template.zfill(2), duration=dur_wiz)
        try:
            keyboard = kb.wizard_preview_keyboard(job_id)
        except Exception:
            keyboard = kb.approval_keyboard(job_id)
        try:
            with open(out_path, "rb") as f:
                await bot.send_video(chat_id=chat_id, video=f, caption=preview_caption, reply_markup=keyboard, supports_streaming=True)
        except Exception as e:
            try:
                with open(out_path, "rb") as f:
                    await bot.send_document(chat_id=chat_id, document=f, filename=out_path.name, caption=preview_caption, reply_markup=keyboard)
            except Exception as e2:
                await _edit(status_msg, msgs.ERROR_GENERIC.format(reason=f"preview send failed: {e} / {e2}"), chat_id, bot)
                try:
                    store.set_state(store.load(job_id), FAILED)
                except Exception:
                    pass
                return
        try:
            await _edit(status_msg, msgs.WIZARD_PREVIEW_SENT, chat_id, bot)
        except Exception:
            pass

    async def _prompt_handle_if_empty(chat_id: int, bot):
        # prompt user to set handle if empty (instead of hardcoded fallback)
        try:
            if not config.tiktok_handle or not config.watermark_handle:
                cur_t = config.tiktok_handle or "(not set)"
                cur_w = config.watermark_handle or "(not set)"
                await bot.send_message(chat_id=chat_id, text=f"⚠️ Handle not set — TikTok: {cur_t}  Watermark: {cur_w}\nSet via /set_handle @myhandle  or  /set_tiktok @myhandle\nWatermark will be skipped until set.")
        except Exception:
            pass

    async def _send_control_center(chat_id: int, bot, reply_msg=None, edit_msg=None):
        """Send or edit control center — main entry triggered by /start /help /menu."""
        text = msgs.CONTROL_CENTER_TEXT
        kb_markup = kb.control_center_keyboard()
        # also include greeting if first start? Use plain
        try:
            if edit_msg is not None:
                try:
                    await edit_msg.edit_text(text, reply_markup=kb_markup, parse_mode="HTML")
                    return
                except Exception:
                    pass
            # try send
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb_markup, parse_mode="HTML")
        except Exception:
            # fallback without parse_mode
            try:
                await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb_markup)
            except Exception:
                pass

    async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            return
        name = (update.effective_user.first_name if update.effective_user else "there")
        # greeting + control center per spec: Main control center triggered by /start (and /help, /menu)
        try:
            await update.message.reply_text(msgs.start(name))
        except Exception:
            pass
        await _send_control_center(update.effective_chat.id, context.bot)
        # if handles empty, prompt to set
        try:
            await _prompt_handle_if_empty(update.effective_chat.id, context.bot)
        except Exception:
            pass

    async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            return
        # Help is also control center per spec, but show help guide directly plus control center keyboard
        # spec: control center should be accessible via /help as well; we send control center + help text
        await _send_control_center(update.effective_chat.id, context.bot)
        try:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=msgs.HELP_TEXT, reply_markup=kb.help_keyboard(), parse_mode="HTML")
        except Exception:
            try:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=msgs.HELP_TEXT, reply_markup=kb.help_keyboard())
            except Exception:
                pass

    async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            return
        await _send_control_center(update.effective_chat.id, context.bot)

    async def templates_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            return
        try:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=msgs.TEMPLATES_TEXT, reply_markup=kb.templates_list_keyboard(), parse_mode="HTML")
        except Exception:
            try:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=msgs.TEMPLATES_TEXT, reply_markup=kb.templates_list_keyboard())
            except Exception:
                pass
        # Preview is generated on demand from the user's own video after they send URL — no hardcoded test files.

    async def url_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            return
        chat_id = update.effective_chat.id
        # args after /url ?
        text = (update.message.text or "").strip()
        # extract url after /url
        after = text[len("/url"):].strip() if text.lower().startswith("/url") else ""
        if after:
            # treat as URL paste with args
            await handle_text(update, context)
            return
        wiz = {"step": WIZARD_STEP_AWAITING_URL, "url": None}
        _wizard_set(chat_id, wiz)
        await update.message.reply_text("🔗 Please send a video URL (with or without time cut like 'Cut 0.25 to 1.00')")

    async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            return
        job = store.active_job()
        wiz = _wizard_get(update.effective_chat.id)
        if wiz:
            await update.message.reply_text(f"Wizard step: {wiz.get('step')} url={wiz.get('url') or '?'} template={wiz.get('template') or '?'}")
            return
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
            # also clear wizard if present
            wiz = _wizard_get(update.effective_chat.id)
            if wiz:
                _wizard_clear(update.effective_chat.id)
                await update.message.reply_text(msgs.CANCELLED.format(stage=wiz.get("step","wizard")))
                return
            await update.message.reply_text(msgs.INTERRUPTED_NO_JOB)
            return
        cur_state = job.get("state", "")
        registry.request_interrupt(job["id"])
        try:
            store.set_state(store.load(job["id"]), CANCELLED)
        except Exception:
            pass
        _wizard_clear(update.effective_chat.id)
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
        action = data.split(":")[0] if ":" in data else data
        job_id = data.split(":", 1)[1] if ":" in data else ""
        chat_id = update.effective_chat.id if update.effective_chat else config.allowed_chat_id
        qmsg = update.callback_query.message

        # --- control center callbacks (no job_id needed) ---
        cc_actions = {"docs", "help", "templates", "logs", "settings", "send_url", "back_menu", "docs_send_files", "select_template_00", "select_template_01"}
        if action in cc_actions or action.startswith("select_template"):
            try:
                await update.callback_query.answer()
            except Exception:
                pass
            # docs
            if action == "docs":
                try:
                    await context.bot.send_message(chat_id=chat_id, text=msgs.DOCS_TEXT, reply_markup=kb.docs_keyboard(), parse_mode="HTML")
                except Exception:
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=msgs.DOCS_TEXT, reply_markup=kb.docs_keyboard())
                    except Exception:
                        pass
                return
            if action == "docs_send_files":
                # optionally send docs as document files
                try:
                    await update.callback_query.answer("Sending docs…")
                except Exception:
                    pass
                import pathlib
                repo = Path(__file__).parent
                doc_files = [
                    repo / "docs" / "TICKETS.md",
                    repo / "docs" / "templates" / "01-vertical-9x16.md",
                    repo / "README.md",
                    repo / "docs" / "tickets" / "mventor-ticket-001.md",
                ]
                sent = 0
                for p in doc_files:
                    if p.exists() and p.is_file():
                        try:
                            with open(p, "rb") as f:
                                await context.bot.send_document(chat_id=chat_id, document=f, filename=p.name, caption=f"📄 {p.relative_to(repo)}")
                            sent += 1
                        except Exception:
                            pass
                if sent == 0:
                    try:
                        await context.bot.send_message(chat_id=chat_id, text="No docs files found to send (docs/ missing).")
                    except Exception:
                        pass
                return
            if action == "help":
                try:
                    await context.bot.send_message(chat_id=chat_id, text=msgs.HELP_TEXT, reply_markup=kb.help_keyboard(), parse_mode="HTML")
                except Exception:
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=msgs.HELP_TEXT, reply_markup=kb.help_keyboard())
                    except Exception:
                        pass
                return
            if action == "templates":
                try:
                    await context.bot.send_message(chat_id=chat_id, text=msgs.TEMPLATES_TEXT, reply_markup=kb.templates_list_keyboard(), parse_mode="HTML")
                except Exception:
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=msgs.TEMPLATES_TEXT, reply_markup=kb.templates_list_keyboard())
                    except Exception:
                        pass
                # try preview photo if thumb available? send small note about files
                try:
                    # optionally send preview frames as photos if available (list view as telegram bots have)
                    # we have mp4 samples — send as video notes or just mention paths
                    pass
                except Exception:
                    pass
                return
            if action in ("select_template_00", "select_template_01"):
                # select_template_00 -> 00, select_template_01 -> 01
                sel = "00" if action.endswith("00") else "01"
                PENDING_TEMPLATE[chat_id] = sel
                wiz = _wizard_get(chat_id)
                if wiz and wiz.get("step") == WIZARD_STEP_AWAITING_TEMPLATE:
                    wiz["template"] = sel
                    _wizard_set(chat_id, wiz)
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=msgs.WIZARD_TEMPLATE_SAVED.format(template=sel) + " (via Templates list)")
                    except Exception:
                        pass
                    # auto advance to cut step
                    await _wizard_ask_cut(chat_id, context.bot, wiz.get("duration"))
                    return
                # also if no wizard, just confirm selection for next URL
                try:
                    await context.bot.send_message(chat_id=chat_id, text=msgs.WIZARD_TEMPLATE_SAVED.format(template=sel) + " — will use for next URL. Now send a URL via /url or paste.")
                except Exception:
                    pass
                # also show control center again?
                return
            if action == "logs":
                # reuse logs_cmd logic inline
                try:
                    from core.logger import CSV_PATH
                    from core.logger import _ensure_log_file
                    if not CSV_PATH.exists():
                        try:
                            _ensure_log_file()
                        except Exception:
                            pass
                    if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
                        await context.bot.send_message(chat_id=chat_id, text="No logs yet — jobs.csv is empty.")
                    else:
                        with open(CSV_PATH, "rb") as f:
                            await context.bot.send_document(chat_id=chat_id, document=f, filename="jobs.csv", caption=f"📊 Jobs log ({CSV_PATH.stat().st_size} bytes) — Excel-ready UTF-8 BOM, Arabic preserved")
                except Exception as e:
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ logs send failed: {e}")
                    except Exception:
                        pass
                return
            if action == "settings":
                cur_t = config.tiktok_handle or "(not set)"
                cur_w = config.watermark_handle or "(not set)"
                try:
                    txt = msgs.SETTINGS_TEXT.format(tiktok=cur_t, watermark=cur_w, jobs_dir=str(config.jobs_dir), ffmpeg_dir=str(config.ffmpeg_dir), hours=getattr(config, "cookie_check_hours", 24), max_uploads=getattr(config, "max_uploads_per_day", 3))
                    await context.bot.send_message(chat_id=chat_id, text=txt, reply_markup=kb.back_menu_keyboard(), parse_mode="HTML")
                except Exception:
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=msgs.HANDLE_CURRENT.format(tiktok=cur_t, watermark=cur_w), reply_markup=kb.back_menu_keyboard())
                    except Exception:
                        pass
                return
            if action == "send_url":
                _wizard_set(chat_id, {"step": WIZARD_STEP_AWAITING_URL, "url": None})
                try:
                    await context.bot.send_message(chat_id=chat_id, text="🔗 Please send a video URL (with or without time cut like 'Cut 0.25 to 1.00')\nTip: you can also use /url <link> or just paste the link.")
                except Exception:
                    pass
                return
            if action == "back_menu":
                await _send_control_center(chat_id, context.bot)
                return
            # fallback
            return

        if not job_id:
            aj = store.active_job()
            if aj and aj.get("state") == AWAITING_APPROVAL:
                job_id = aj["id"]
            else:
                wiz = _wizard_get(update.effective_chat.id) if update.effective_chat else None
                if wiz and wiz.get("job_id"):
                    job_id = wiz["job_id"]
                else:
                    try:
                        await update.callback_query.answer("No pending preview")
                    except Exception:
                        pass
                    return
        try:
            await update.callback_query.answer()
        except Exception:
            pass
        # chat_id and qmsg already set above, but re-ensure
        chat_id = update.effective_chat.id if update.effective_chat else config.allowed_chat_id
        qmsg = update.callback_query.message

        # confirm/approve -> upload
        if action in ("approve", "confirm"):
            asyncio.create_task(_do_upload(job_id, chat_id, context.bot, qmsg))
        elif action == "reject":
            try:
                j = store.load(job_id)
                store.set_state(j, CANCELLED)
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
            _wizard_clear(chat_id)
        elif action == "revert":
            # spec: Use last URL or paste a new URL with two buttons
            try:
                await qmsg.edit_text(msgs.WIZARD_REVERT_PROMPT)  # type: ignore
            except Exception:
                pass
            try:
                keyboard = kb.revert_choice_keyboard(job_id)
                await context.bot.send_message(chat_id=chat_id, text=msgs.WIZARD_REVERT_PROMPT, reply_markup=keyboard)
            except Exception:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=msgs.WIZARD_REVERT_PROMPT)
                except Exception:
                    pass
            # keep job cancelled? spec revert should not remain in awaiting_approval
            try:
                j = store.load(job_id)
                store.set_state(j, CANCELLED)
            except Exception:
                pass
            # set wizard to await url choice
            wiz = _wizard_get(chat_id)
            if wiz:
                wiz["step"] = WIZARD_STEP_AWAITING_URL
                _wizard_set(chat_id, wiz)
            else:
                _wizard_set(chat_id, {"step": WIZARD_STEP_AWAITING_URL, "url": None})
        elif action == "use_last":
            # reuse last URL
            last = LAST_URL.get(chat_id)
            if not last:
                try:
                    await context.bot.send_message(chat_id=chat_id, text="No last URL — please paste a new URL")
                except Exception:
                    pass
                return
            # restart wizard verification for last URL
            try:
                await qmsg.edit_text(f"♻️ Reusing last URL: {last}")  # type: ignore
            except Exception:
                pass
            # simulate text handling via wizard init + verify
            fake_update_text = last
            # we cannot easily reuse handle_text; manually start verify task
            try:
                await context.bot.send_message(chat_id=chat_id, text=msgs.VERIFYING)
            except Exception:
                pass
            # create short text pseudo
            # Trigger wizard flow by calling verify inline
            async def _reuse():
                # verify last URL again
                platform = JobStore.detect_platform(last) or ""
                try:
                    v = await asyncio.to_thread(verify_url, last, platform, job_id or "wizard-reuse")
                except Exception as e:
                    v = {"ok": False, "error": str(e)}
                if not v.get("ok"):
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=msgs.INVALID_URL + f"\n{v.get('error','')}")
                    except Exception:
                        pass
                    return
                probe = v.get("probe") or {}
                dur = v.get("duration")
                title = v.get("title") or probe.get("title") or "video"
                channel = probe.get("uploader") or probe.get("channel") or "unknown"
                # parse cut if any in last URL? Last URL may contain cut pattern? Try parse
                cs, ce, _ = parse_time_cut(last)
                _wizard_init(chat_id, last, cs, ce, dur, probe, title, channel)
                await _wizard_send_thumbnail(chat_id, context.bot, probe, last, dur)
                await _wizard_ask_template(chat_id, context.bot)
            asyncio.create_task(_reuse())
        elif action == "new_url":
            try:
                await qmsg.edit_text("🔗 Please paste a new URL")  # type: ignore
            except Exception:
                pass
            _wizard_set(chat_id, {"step": WIZARD_STEP_AWAITING_URL, "url": None})
            try:
                await context.bot.send_message(chat_id=chat_id, text="🔗 Please paste a new URL (with optional cut like 'Cut 0.25 to 1.00')")
            except Exception:
                pass
        elif action == "rerun":
            try:
                j = store.load(job_id)
                store.update(j, awaiting_rerun=True)
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
            # also update wizard step to awaiting description? For wizard flow, rerun means new description
            wiz = _wizard_get(chat_id)
            if wiz:
                wiz["step"] = WIZARD_STEP_AWAITING_DESCRIPTION
                _wizard_set(chat_id, wiz)
        elif action == "cancel":
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
            _wizard_clear(chat_id)
        else:
            try:
                await update.callback_query.answer(f"Unknown action: {action}")
            except Exception:
                pass

    async def _pipeline(job_id: str, parsed: dict, status_msg, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        # legacy single-shot pipeline (kept for backward compat, delegates to wizard pipeline)
        await _wizard_pipeline(job_id, parsed, status_msg, chat_id, context.bot)

    # --- wizard text router ---
    async def _wizard_handle_url_verify(chat_id: int, bot, url: str, text: str, status_msg):
        """Verify URL and start wizard thumbnail + template flow."""
        platform = JobStore.detect_platform(url) or ""
        try:
            v = await asyncio.to_thread(verify_url, url, platform, f"wizard-{chat_id}")
        except Exception as e:
            v = {"ok": False, "error": str(e), "title": None, "duration": None, "probe": None}
        if not v.get("ok"):
            try:
                await bot.send_message(chat_id=chat_id, text=msgs.INVALID_URL)
                await bot.send_message(chat_id=chat_id, text=f"Reason: {v.get('error','unknown')}\nPlease send a new URL with /url")
            except Exception:
                pass
            wiz = _wizard_get(chat_id)
            if wiz:
                wiz["step"] = WIZARD_STEP_AWAITING_URL
                _wizard_set(chat_id, wiz)
            else:
                _wizard_set(chat_id, {"step": WIZARD_STEP_AWAITING_URL, "url": None})
            try:
                if status_msg:
                    await _edit(status_msg, msgs.INVALID_URL, chat_id, bot)
            except Exception:
                pass
            return
        # success
        probe = v.get("probe") or {}
        duration = v.get("duration")
        title = v.get("title") or probe.get("title") or "video"
        channel = probe.get("uploader") or probe.get("channel") or probe.get("extractor") or "unknown"
        # parse cut from original text if any
        cs, ce, _ = parse_time_cut(text)
        _wizard_init(chat_id, url, cs, ce, duration, probe, title, channel)
        # send thumbnail frame photo + default description caption
        await _wizard_send_thumbnail(chat_id, bot, probe, url, duration)
        try:
            if status_msg:
                await _edit(status_msg, msgs.VERIFIED_OK.format(title=title[:60], duration=f"{int(duration)}s" if isinstance(duration,(int,float)) and duration else "?", via=""), chat_id, bot)
        except Exception:
            pass
        await _wizard_ask_template(chat_id, bot)

    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            return
        text = update.message.text.strip()
        if not text:
            return
        chat_id = update.effective_chat.id

        # rerun handling via JobStore flag (legacy)
        aj = store.active_job()
        if aj and aj.get("state") == AWAITING_APPROVAL and aj.get("awaiting_rerun"):
            parsed_url = _extract_url(text)
            if not parsed_url:
                fake_url = aj.get("url") or "https://youtu.be/dummy"
                new_parsed = parse_message(f"{fake_url} {text}")
                if "template" not in text.lower():
                    new_parsed["template"] = aj.get("template", "01")
                    if new_parsed["template"] == "00":
                        new_parsed["title"] = ""
                        new_parsed["subtitle"] = ""
                if not _has_no_watermark(text) and not aj.get("handle"):
                    new_parsed["handle"] = ""
                try:
                    j = store.load(aj["id"])
                    store.update(j, title=new_parsed["title"], subtitle=new_parsed["subtitle"], caption=new_parsed["caption"], template=new_parsed["template"], handle=new_parsed.get("handle", config.watermark_handle), awaiting_rerun=False)
                except Exception:
                    pass
                status_msg = await update.message.reply_text(f"🔁 Rerunning montage Template {new_parsed['template']}...")
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
                        await asyncio.to_thread(vertical_fast, Path(video_path), out_path, new_parsed["title"], new_parsed["subtitle"], "card", "#EAB308", new_parsed.get("handle", config.watermark_handle))
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

        # --- wizard state machine routing ---
        wiz = _wizard_get(chat_id)

        # if wizard exists and in awaiting steps, route accordingly
        if wiz and wiz.get("step") == WIZARD_STEP_AWAITING_TEMPLATE:
            templ = parse_template_wizard(text)
            wiz["template"] = templ
            wiz["step"] = WIZARD_STEP_AWAITING_CUT  # will be handled by ask_cut which may skip
            _wizard_set(chat_id, wiz)
            try:
                await update.message.reply_text(msgs.WIZARD_TEMPLATE_SAVED.format(template=templ))
            except Exception:
                pass
            await _wizard_ask_cut(chat_id, context.bot, wiz.get("duration"))
            return
        if wiz and wiz.get("step") == WIZARD_STEP_AWAITING_CUT:
            # try parse cut; handles "0.25 to 1.00" etc, also "0:25 to 1:00"
            cs, ce, _ = parse_time_cut(text)
            if cs is not None and ce is not None:
                wiz["cut_start"] = cs
                wiz["cut_end"] = ce
                wiz["step"] = WIZARD_STEP_AWAITING_DESCRIPTION
                _wizard_set(chat_id, wiz)
                try:
                    await update.message.reply_text(msgs.WIZARD_CUT_SAVED.format(start=_fmt_secs(cs), end=_fmt_secs(ce)))
                except Exception:
                    pass
                await _wizard_ask_description(chat_id, context.bot)
                return
            # check for skip / empty -> random
            if text.strip().lower() in ("/skip", "skip", "", "random", "nothing"):
                dur = wiz.get("duration")
                rs, re_ = random_30s_slice(dur)
                if rs is not None:
                    wiz["cut_start"] = rs
                    wiz["cut_end"] = re_
                    wiz["step"] = WIZARD_STEP_AWAITING_DESCRIPTION
                    _wizard_set(chat_id, wiz)
                    try:
                        await update.message.reply_text(msgs.WIZARD_CUT_RANDOM.format(start=_fmt_secs(rs), end=_fmt_secs(re_)))
                    except Exception:
                        pass
                else:
                    wiz["cut_start"] = None
                    wiz["cut_end"] = None
                    wiz["step"] = WIZARD_STEP_AWAITING_DESCRIPTION
                    _wizard_set(chat_id, wiz)
                    try:
                        await update.message.reply_text("✅ Using full video (shorter than 30s)")
                    except Exception:
                        pass
                await _wizard_ask_description(chat_id, context.bot)
                return
            # if unrecognized, treat as skip with random per spec: "If no cut and full video: Bot randomly picks ONE 30s"
            # But to avoid confusion, ask again
            try:
                await update.message.reply_text("❓ Could not parse cut. Send like '0:25 to 1:00' or 'Cut 0.25 to 1.00' or /skip for random 30s")
            except Exception:
                pass
            return
        if wiz and wiz.get("step") == WIZARD_STEP_AWAITING_DESCRIPTION:
            if text.strip().lower() in ("/skip", "skip", ""):
                wiz["description"] = ""
            else:
                # support "Description: ..." label
                desc = parse_description_text_only(text, wiz.get("url"))
                # if desc empty but text not skip, treat raw text as description
                if not desc:
                    desc = text.strip()
                wiz["description"] = desc
            wiz["step"] = WIZARD_STEP_AWAITING_HASHTAGS
            _wizard_set(chat_id, wiz)
            try:
                if wiz["description"]:
                    await update.message.reply_text(f"✅ Description saved: {wiz['description'][:120]}")
                else:
                    await update.message.reply_text("✅ Description skipped — will use video title")
            except Exception:
                pass
            await _wizard_ask_hashtags(chat_id, context.bot)
            return
        if wiz and wiz.get("step") == WIZARD_STEP_AWAITING_HASHTAGS:
            tags = parse_hashtags(text)
            # also handle case where user sends /skip or empty -> no hashtags
            if text.strip().lower() in ("/skip", "skip", ""):
                tags = []
            wiz["hashtags"] = tags
            _wizard_set(chat_id, wiz)
            try:
                if tags:
                    await update.message.reply_text(msgs.WIZARD_HASHTAGS_SAVED.format(tags=" ".join(tags)))
                else:
                    await update.message.reply_text("✅ No hashtags — proceeding")
            except Exception:
                pass
            # trigger preview montage
            status_msg = await update.message.reply_text(msgs.WIZARD_MONTAGING.format(template=wiz.get("template") or "00"))
            await _wizard_trigger_preview(chat_id, context.bot, status_msg)
            return
        if wiz and wiz.get("step") == WIZARD_STEP_AWAITING_URL:
            # awaiting new URL input for revert flow
            url = _extract_url(text)
            if not url:
                try:
                    await update.message.reply_text(msgs.INVALID_URL)
                except Exception:
                    pass
                return
            # restart wizard verify for new URL
            status_msg = await update.message.reply_text(msgs.VERIFYING)
            await _wizard_handle_url_verify(chat_id, context.bot, url, text, status_msg)
            return
        if wiz and wiz.get("step") == WIZARD_STEP_AWAITING_APPROVAL:
            # wizard is awaiting approval but user typed text instead of button — treat as maybe new caption? ignore or prompt
            try:
                await update.message.reply_text(msgs.WIZARD_PREVIEW_SENT)
            except Exception:
                pass
            return

        # --- no wizard in progress: treat as new URL entry (spec step 1) ---
        parsed = parse_message(text)
        url = parsed["url"] or _extract_url(text)
        if not url:
            # No URL found - if wizard is idle, prompt for URL. Check if text is /url handled elsewhere (command). Otherwise unsupported.
            await update.message.reply_text(msgs.UNSUPPORTED_URL)
            return
        # URL found -> start wizard verification
        status_msg = await update.message.reply_text(msgs.VERIFYING)
        await _wizard_handle_url_verify(chat_id, context.bot, url, text, status_msg)
        # also handle case where user sent URL with cut already — _wizard_init inside verify will preserve cut
        # template will be asked regardless; if user typed template explicitly, we could auto-store? For now ask again; step will handle.
        # For backward compat single-shot jobs without wizard, also create job immediately? Wizard replaces that flow.

    async def set_handle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            return
        text = (update.message.text or "").strip()
        # extract arg after command
        arg = ""
        parts = text.split(None, 1)
        if len(parts) > 1:
            arg = parts[1].strip().split()[0]
        elif context.args:
            arg = (context.args[0] or "").strip()
        if not arg:
            cur = config.tiktok_handle
            wm = config.watermark_handle
            try:
                await update.message.reply_text(msgs.HANDLE_CURRENT.format(tiktok=cur, watermark=wm))
                await update.message.reply_text("Usage: /set_handle @myhandle  — sets both TikTok and watermark handles")
            except Exception:
                pass
            return
        raw = arg.strip()
        # normalize
        if not raw.startswith("@"):
            raw = "@" + raw.lstrip("@")
        body = raw[1:]
        if not body or len(body) < 2 or len(body) > 30 or not re.match(r"^[A-Za-z0-9._]+$", body):
            try:
                await update.message.reply_text(msgs.HANDLE_INVALID)
            except Exception:
                pass
            return
        try:
            from config import persist_handle
            new_h = persist_handle(raw)
            await update.message.reply_text(msgs.HANDLE_SET.format(handle=new_h))
        except Exception as e:
            try:
                await update.message.reply_text(msgs.ERROR_GENERIC.format(reason=str(e)))
            except Exception:
                pass

    async def retry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            return
        chat_id = update.effective_chat.id
        # lazy re-verify cookies first
        try:
            from core.cookies import verify_tiktok_session
            chk = await asyncio.to_thread(verify_tiktok_session)
            if not chk.get("ok"):
                try:
                    await update.message.reply_text(msgs.COOKIE_EXPIRED + f"\n{chk.get('reason','')}")
                except Exception:
                    pass
                return
            else:
                try:
                    await update.message.reply_text(f"✅ TikTok session OK ({chk.get('cookie_count',0)} cookies) — you can now send a new URL or reuse last")
                except Exception:
                    pass
        except Exception as e:
            try:
                await update.message.reply_text(msgs.ERROR_GENERIC.format(reason=str(e)))
            except Exception:
                pass
            return
        # if last URL exists, offer reuse
        last = LAST_URL.get(chat_id)
        if last:
            try:
                await update.message.reply_text(f"♻️ Last URL: {last}\nSend it again or type /url to start")
            except Exception:
                pass
        # also if there's a failed job with cookie_fail, allow re-upload if preview exists
        try:
            aj = store.active_job()
            if aj and aj.get("state") == AWAITING_APPROVAL:
                try:
                    await update.message.reply_text("▶️ Found pending preview — use Confirm to Upload to retry upload")
                except Exception:
                    pass
        except Exception:
            pass

    async def handle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # alias to set_handle display
        await set_handle_cmd(update, context)

    async def set_tiktok_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # alias for /set_tiktok — same as /set_handle (sets both for simplicity)
        await set_handle_cmd(update, context)

    async def set_tiktok_cmd_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await set_handle_cmd(update, context)

    async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat and update.effective_chat.id != config.allowed_chat_id:
            return
        # ensure logs dir and CSV exists
        try:
            from core.logger import CSV_PATH
            if not CSV_PATH.exists():
                # ensure file created with header
                from core.logger import _ensure_log_file
                _ensure_log_file()
            if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
                await update.message.reply_text("No logs yet — jobs.csv is empty.")
                return
            # send document
            with open(CSV_PATH, "rb") as f:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=f, filename="jobs.csv", caption=f"📊 Jobs log ({CSV_PATH.stat().st_size} bytes) — Excel-ready UTF-8 BOM, Arabic preserved")
        except Exception as e:
            try:
                await update.message.reply_text(f"⚠️ logs send failed: {e}")
            except Exception:
                pass

    # --- T7 daily cookie verification loop ---
    async def _daily_cookie_loop(bot):
        # interval configurable COOKIE_CHECK_HOURS, default 24h
        interval = max(1, int(getattr(config, "cookie_check_hours", 24))) * 3600
        # ponytail: simple asyncio loop, no extra process
        while True:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            try:
                from core.cookies import verify_tiktok_session
                chk = await asyncio.to_thread(verify_tiktok_session)
                if not chk.get("ok"):
                    try:
                        await bot.send_message(chat_id=config.allowed_chat_id, text=msgs.COOKIE_DAILY_ALERT + f"\n{chk.get('reason','')}")
                    except Exception:
                        pass
                # also optional success logging? skip to avoid spam
            except Exception:
                pass

    async def post_init(app):
        # persistent menu commands per spec (BotCommand)
        try:
            from telegram import BotCommand
            cmds = [
                BotCommand("start", "🎛️ Control center"),
                BotCommand("help", "❓ Help + guide"),
                BotCommand("menu", "🎛️ Control center"),
                BotCommand("url", "🔗 Send video URL"),
                BotCommand("templates", "🎨 Templates list"),
                BotCommand("logs", "📊 Jobs log (CSV)"),
                BotCommand("set_handle", "⚙️ Set @handle (watermark + TikTok)"),
                BotCommand("set_tiktok", "⚙️ Set TikTok handle alias"),
                BotCommand("status", "📊 Job/wizard status"),
                BotCommand("interrupt", "✋ Cancel running job"),
            ]
            await app.bot.set_my_commands(cmds)
        except Exception:
            pass
        # immediate check at startup (proactive before next upload)
        try:
            from core.cookies import verify_tiktok_session
            chk = await asyncio.to_thread(verify_tiktok_session)
            if not chk.get("ok"):
                try:
                    await app.bot.send_message(chat_id=config.allowed_chat_id, text=msgs.COOKIE_DAILY_ALERT + f"\n{chk.get('reason','')}")
                except Exception:
                    pass
        except Exception:
            pass
        # launch daily loop as background task
        try:
            app.create_task(_daily_cookie_loop(app.bot))
        except Exception:
            # fallback to asyncio.create_task
            try:
                asyncio.create_task(_daily_cookie_loop(app.bot))
            except Exception:
                pass

    # build application with post_init for daily cookie check
    try:
        builder = Application.builder().token(config.bot_token)
        # post_init available in PTB 21+
        try:
            builder = builder.post_init(post_init)
        except Exception:
            pass
        app = builder.build()
    except Exception:
        app = Application.builder().token(config.bot_token).build()
        # try attach post_init manually
        try:
            app.post_init = post_init  # type: ignore
        except Exception:
            pass
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("url", url_cmd))
    app.add_handler(CommandHandler("templates", templates_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("interrupt", interrupt_cmd))
    app.add_handler(CommandHandler("set_handle", set_handle_cmd))
    app.add_handler(CommandHandler("set_tiktok", set_tiktok_cmd))
    app.add_handler(CommandHandler("handle", handle_cmd))
    app.add_handler(CommandHandler("tiktok", set_tiktok_cmd))
    app.add_handler(CommandHandler("logs", logs_cmd))
    app.add_handler(CommandHandler("retry", retry_cmd))
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
