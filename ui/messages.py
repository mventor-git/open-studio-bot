"""All user-visible Telegram strings live here (single source, easy to tune)."""

import html
import re
from pathlib import Path


def _md_to_telegram_html(md: str) -> str:
    """Convert markdown to Telegram HTML: strip leading #'s -> <b>, handle code blocks/inline."""
    if not md:
        return ""
    # preserve fenced code blocks ```...``` -> <pre>
    code_blocks: list[str] = []

    def _repl_fence(m: re.Match) -> str:
        content = m.group(1) or ""
        # strip leading language tag line if present already handled; content is inner
        # content may include leading \n, strip first newline
        if content.startswith("\n"):
            content = content[1:]
        escaped = html.escape(content, quote=False)
        placeholder = f"__CODEBLOCK_{len(code_blocks)}__"
        code_blocks.append(f"<pre>{escaped}</pre>")
        return placeholder

    # match ```...``` with optional language
    md_processed = re.sub(r"```(?:\w+)?\n?(.*?)```", _repl_fence, md, flags=re.S)

    lines: list[str] = []
    for line in md_processed.splitlines():
        m = re.match(r"^\s*#{1,6}\s*(.*)$", line)
        if m:
            content = m.group(1).strip()
            if not content:
                continue
            # escape html inside header, then bold
            content_esc = html.escape(content, quote=False)
            # handle inline `code` inside header before escaping? already escaped, so do after? simple bold
            lines.append(f"<b>{content_esc}</b>")
        else:
            lines.append(line)
    text = "\n".join(lines)

    # inline `code` -> <code>
    def _repl_inline(m: re.Match) -> str:
        inner = html.escape(m.group(1), quote=False)
        return f"<code>{inner}</code>"

    text = re.sub(r"`([^`\n]+)`", _repl_inline, text)
    # markdown **bold** -> <b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    for i, block in enumerate(code_blocks):
        text = text.replace(f"__CODEBLOCK_{i}__", block)

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _read_readme_formatted() -> str | None:
    """Read README.md (app readme) and format for Telegram HTML. Returns None if missing."""
    try:
        # repo root is parent of ui/
        repo_root = Path(__file__).resolve().parent.parent
        readme = repo_root / "README.md"
        if not readme.exists():
            return None
        raw = readme.read_text(encoding="utf-8", errors="replace")
        # limit raw size to avoid Telegram 4096 overflow
        if len(raw) > 8000:
            raw = raw[:8000] + "\n\n…(truncated)"
        formatted = _md_to_telegram_html(raw)
        # headers stripped -> no markdown hash headers remain for Telegram
        # and truncate for Telegram message limit (4096 chars, leave 500 for wrapper)
        if len(formatted) > 3500:
            formatted = formatted[:3500].rsplit("\n", 1)[0] + "\n\n…(truncated, see file)"
        # prepend title if not already bold title
        if not formatted.lstrip().startswith("<b>"):
            formatted = f"📚 <b>Docs — Open Studio Bot</b>\n\n{formatted}"
        return formatted
    except Exception:
        return None


def get_docs_text() -> str:
    """Return Telegram-friendly docs about the app (README formatted). Fallback to DOCS_TEXT."""
    formatted = _read_readme_formatted()
    if formatted:
        return formatted
    # fallback: DOCS_TEXT about app, handle placeholder -> actual handle
    try:
        from config import config  # lazy
        h = (getattr(config, "watermark_handle", "") or "").strip()
        if not h:
            h = "(not set — use /set_handle)"
        elif h.startswith("@") is False:
            h = "@" + h.lstrip("@")
    except Exception:
        h = "(not set — use /set_handle)"
    fallback = DOCS_TEXT
    if "{handle}" in fallback:
        fallback = fallback.replace("{handle}", h)
    return fallback


def get_templates_text(handle: str | None = None) -> str:
    """Return templates text with current watermark handle inserted (configurable via /set_handle)."""
    try:
        if handle is None:
            try:
                from config import config  # lazy to avoid cycle at import
                handle = (getattr(config, "watermark_handle", "") or "").strip()
            except Exception:
                handle = ""
        if not handle:
            handle = "(not set — use /set_handle)"
        elif handle != "(not set — use /set_handle)" and not handle.startswith("@"):
            handle = "@" + handle.lstrip("@")
    except Exception:
        handle = "(not set — use /set_handle)"
    tpl = TEMPLATES_TEXT
    if "{handle}" in tpl:
        return tpl.replace("{handle}", handle)
    # fallback: replace legacy placeholder if any hardcoded remains (should not happen)
    return tpl


def get_help_text(handle: str | None = None) -> str:
    """Help with dynamic handle."""
    try:
        if handle is None:
            from config import config
            handle = (getattr(config, "watermark_handle", "") or "").strip()
            if not handle:
                handle = "(not set — use /set_handle)"
            elif not handle.startswith("@"):
                handle = "@" + handle.lstrip("@")
    except Exception:
        handle = "(not set — use /set_handle)"
    txt = HELP_TEXT
    if "{handle}" in txt:
        return txt.replace("{handle}", handle)
    return txt


def start(name: str) -> str:
    return (
        f"👋 Hi {name}!\n\n"
        "Send me a video link (YouTube / Instagram / Facebook / TikTok) "
        "optionally with a prompt to montage it.\n\n"
        "Commands:\n"
        "/status — current job state\n"
        "/interrupt — cancel the running job"
    )


UNSUPPORTED_URL = (
    "❌ Unsupported link. I understand YouTube, Instagram, Facebook and TikTok URLs.\n"
    "Example: https://www.facebook.com/watch/?v=123 make it dramatic"
)

VERIFYING = "🔎 Verifying link..."

VERIFIED_OK = "✅ Verified — “{title}” ({duration}){via}"

VERIFY_FAILED = "❌ Verification failed:\n{reason}"

DOWNLOADING = "⬇️ Downloading..."

DOWNLOADED_OK = "⬇️ Done — video ✓{sound} ({duration})"

SOUND_OK = " sound ✓"
SOUND_MISSING = " sound ✗ (template will add music)"

DOWNLOAD_FAILED = "❌ Download failed:\n{reason}"

MONTAGE_STARTED = (
    "🎬 Montage session started\n"
    "template: {template}\n"
    "prompt: {prompt}"
)

CAPTION_READY = "✍️ Caption written:\n\n{caption}"

UPLOADING = "📤 Uploading to TikTok..."

POSTED = "✅ Posted — {link}"

PREVIEW = "👀 Preview ready — accept or rerun?"
PREVIEW_CAPTION = "Template {template} ready — {dur}s — 1080x1920 — Approve to publish?"
AWAITING_APPROVAL = "👀 Preview sent — awaiting approval (Approve / Rerun / Reject)"
PUBLISHING = "📤 Publishing..."
REJECTED = "❌ Rejected"
RERUN_PROMPT = "Send new Title / Subtitle or Description for rerun"
APPROVED = "✅ Approved — publishing"

CANCELLED = "🛑 Cancelled at stage: {stage}"

JOB_STATE = "Job {job_id}\nstate: {state}\nstage detail: {detail}"

NOT_QUEUED_BY_YOU = "No active job. Send a link to start."

INTERRUPTED_NO_JOB = "Nothing to interrupt."

ERROR_GENERIC = "❌ Something went wrong: {reason}"

CANCEL_BUTTON = "✋ Cancel"
ACCEPT_BUTTON = "✅ Accept"
RERUN_BUTTON = "🔁 Rerun"
REJECT_BUTTON = "❌ Reject"

# --- wizard v2 ---
INVALID_URL = "❌ Invalid or not downloadable — please send a valid video URL (YouTube, TikTok, Instagram, Facebook). Try again with /url"

WIZARD_THUMB_CAPTION = "🎞️ {title}\n📺 {channel}\n⏱️ {duration}"
WIZARD_TEMPLATE_PROMPT = (
    "Select template no. — 00 (raw, no card) or 01 (9:16 + card + watermark) — "
    "type 00 or 01 or nothing (defaults to 00)"
)
WIZARD_TEMPLATE_SAVED = "✅ Template {template} saved"
WIZARD_CUT_PROMPT = "Select cut 00:00 to {end} (video is 00:00-{end}) — send e.g. 0:25 to 1:00 or Cut 0.25 to 1.00 — or send /skip for random 30s"
WIZARD_CUT_SAVED = "✅ Cut {start}-{end} saved"
WIZARD_CUT_RANDOM = "🎲 Random 30s: {start}-{end}"
WIZARD_DESCRIPTION_PROMPT = "Type Description (or skip — I'll take it from the video URL itself) — send /skip or empty to use video title"
WIZARD_HASHTAGS_PROMPT = (
    "Type Hashtags (unlimited, with or without # — e.g., تاريخ حضارة or #تاريخ #حضارة) - I'll normalize to #hashtags"
)
WIZARD_HASHTAGS_SAVED = "✅ Hashtags: {tags}"
WIZARD_MONTAGING = "🎬 Montaging Template {template} (9:16)..."
WIZARD_PREVIEW_CAPTION = "Preview Template {template} — {duration}s — 1080x1920 — Confirm to publish?"
WIZARD_PREVIEW_SENT = "👀 Preview sent — Confirm to Upload / Rerun / Revert"
WIZARD_REVERT_PROMPT = "Use last URL or paste a new URL"
WIZARD_CONFIRM_BUTTON = "✅ Confirm to Upload"
WIZARD_REVERT_BUTTON = "❌ Revert"
WIZARD_USE_LAST_BUTTON = "Use Last URL"
WIZARD_NEW_URL_BUTTON = "New URL"

# --- T7: error taxonomy + cookie/handles ---
COOKIE_EXPIRED = (
    "❌ TikTok session expired — please re-login in Waterfox at tiktok.com then send /retry or new URL\n"
    "❌ انتهت جلسة تيك توك — سجل دخولك مرة أخرى في Waterfox على tiktok.com ثم أرسل /retry"
)
COOKIE_DAILY_ALERT = (
    "⚠️ Daily check: TikTok cookies expiring/invalid — please re-login in Waterfox\n"
    "⚠️ فحص يومي: جلسة تيك توك منتهية أو غير صالحة — سجل دخولك مرة أخرى في Waterfox"
)
COOKIE_EXPIRED_SHORT = "❌ TikTok session expired — please re-login in Waterfox at tiktok.com then send /retry or new URL"

DOWNLOAD_FAIL_MSG = "❌ Download failed: {reason}\n❌ فشل التحميل: {reason}"
MONTAGE_FAIL_MSG = "❌ Montage failed: {reason}\n❌ فشل المونتاج: {reason}"
CAPTION_FAIL_MSG = "❌ Caption failed: {reason}\n❌ فشل كتابة الوصف: {reason}"
UPLOAD_FAIL_MSG = "❌ Upload failed: {reason}\n❌ فشل الرفع: {reason}"
UPLOAD_FAILED = UPLOAD_FAIL_MSG  # alias for compat

HANDLE_SET = "Handle set to {handle} — future watermarks and TikTok checks will use it"
HANDLE_INVALID = "❌ Invalid handle — send like /set_handle @myhandle (letters, numbers, _ . allowed)"
HANDLE_CURRENT = "Current handles — TikTok: {tiktok}  Watermark: {watermark}"

# --- control center (Telegram buttons) ---
CONTROL_CENTER_TEXT = (
    "🎛️ <b>Control Center</b> — Open Studio Bot\n"
    "Pick an action:\n"
    "• 📚 Docs — app readme (Telegram → download → montage → TikTok), templates, pipeline\n"
    "• ❓ Help — step-by-step wizard + button guide\n"
    "• 🎨 Templates — list view, tap to select 00 / 01\n"
    "• 📊 Logs — jobs.csv (Excel-ready)\n"
    "• ⚙️ Settings — handles, status, config\n"
    "• 🔗 Send URL — start wizard (/url or paste link)\n\n"
    "Tip: /start /menu /help anytime returns here."
)

HELP_TEXT = (
    "❓ <b>Help — How to use Open Studio Bot</b>\n\n"
    "<b>Step-by-step wizard (v2):</b>\n"
    "1️⃣ <b>Send URL</b> — via /url or paste link (YouTube / TikTok / IG / FB).\n"
    "   Optional cut in same message: <code>Cut 0.25 to 1.00</code> or <code>0:25 to 1:00</code> or <code>26:19 to 27:10</code>.\n"
    "   Bot verifies: must contain video & be downloadable (yt-dlp probe). Else: “Invalid or not downloadable”.\n"
    "2️⃣ <b>Select template</b> — 00 or 01 (empty → 00):\n"
    "   • 00 Raw 9:16 — clean vertical (1080x1920, blurred fill, no card, no burned text) — for clean reposts\n"
    "   • 01 TikTok Card — 9:16 + Majalla card (0.94w × 1.95h, gold #EAB308) + Arabic shaping + watermark {handle} top-left (configurable via /set_handle) — for branded AR\n"
    "   Tap 🎨 Templates or type 00/01.\n"
    "3️⃣ <b>Select cut</b> — <code>00:00 to 00:00</code> or <code>/skip</code> for random 30s.\n"
    "   Shown as “Select cut 00:00 to {duration} (video is 00:00-{duration})”. Random: randint(0, duration-30) → +30s. If &lt;30s, full video.\n"
    "4️⃣ <b>Type Description</b> — or /skip → uses video title via yt-dlp (no hardcoded defaults).\n"
    "   Supports “Description: …” or “Description is: …”.\n"
    "   00: desc = only TikTok post text (never burned). 01: desc burned as card title/subtitle + post text (split on “ - ”).\n"
    "5️⃣ <b>Type Hashtags</b> — unlimited, with/without # (e.g. <code>تاريخ حضارة</code> or <code>#تاريخ #حضارة</code>). Normalized to #hashtags. /skip = none.\n"
    "6️⃣ <b>Preview & Confirm</b> — bot montages (vertical_fast 1080x1920) + sends preview video.\n\n"
    "<b>Buttons we use:</b>\n"
    "• Preview: [✅ Accept] = same as [✅ Confirm to Upload] → upload to TikTok (Joyride Skip → نشر → النشر الآن modal) \n"
    "  [🔁 Rerun] → “Send new Title/Subtitle” — type new text to re-render\n"
    "  [❌ Reject]/[❌ Revert] → cancel or “Use Last URL / New URL”\n"
    "• Revert choice: [Use Last URL] reuses LAST_URL, [New URL] prompts for fresh link\n"
    "• Global: [✋ Cancel] / /interrupt — cancel at any stage; /status — job state\n"
    "• Control center: [📚 Docs] [❓ Help] [🎨 Templates] [📊 Logs] [⚙️ Settings] [🔗 Send URL]\n\n"
    "<b>Examples</b>\n"
    "<code>https://youtu.be/xZDk-vyZm3w - Cut 0.25 to 1.00 Template 01 Description: my title - my subtitle #تاريخ</code>\n"
    "<code>/url https://www.tiktok.com/@user/video/123</code> → then 01 → 0:30 to 1:00 → Description … → hashtags\n"
    "<code>/set_handle {handle}</code> / <code>/set_tiktok {handle}</code> → sets watermark + TikTok handle\n"
)

DOCS_TEXT = (
    "📚 <b>Docs — Open Studio Bot</b>\n\n"
    "<b>What it does</b>\n"
    "Telegram URL (YouTube / TikTok / Instagram / Facebook) → verify (yt-dlp + Waterfox cookies) → download (--download-sections) → montage (vertical_fast 1080x1920, 00 Raw or 01 Card) → preview [Confirm / Rerun / Revert] → upload to TikTok (Playwright نشر → النشر الآن, scroll fix) → Done. State: new → verifying → downloading → montaging → awaiting_approval → uploading → done.\n\n"
    "<b>How to use</b>\n"
    "1. Send URL via /url or paste link (optional cut: <code>Cut 0.25 to 1.00</code> or <code>0:25 to 1:00</code>).\n"
    "2. Pick template: 00 Raw 9:16 (clean, no card) or 01 TikTok Card — 1080×1920 + Majalla card (0.94w × 1.95h, gold #EAB308) + watermark {handle} top-left (configurable via /set_handle).\n"
    "3. Pick cut: <code>00:00 to 00:00</code> or /skip for random 30s (randint 0..duration-30).\n"
    "4. Type Description or /skip → uses video title via yt-dlp. For 01, burned as title/subtitle (split on “ - ”); for 00, only post text.\n"
    "5. Type Hashtags (with or without #, e.g. <code>تاريخ حضارة</code>) or /skip.\n"
    "6. Preview → Confirm to Upload / Rerun / Revert (Use Last URL / New URL).\n\n"
    "<b>Templates</b>\n"
    "• 00 Raw 9:16 — blurred fill (gblur sigma=18) + sharp center, no card, no burned text, watermark {handle} top-left if handle set (skip via --no-watermark). For clean reposts.\n"
    "• 01 TikTok Card — 1080×1920 + Majalla card (0.94w × 1.95h, rounded 22, shadow, gold accent #EAB308 RTL) + Arabic shaping (arabic_reshaper+bidi), watermark {handle} top-left Segoe UI 0.028 (configurable via /set_handle). For branded Arabic. Preview generated on demand.<br>\n"
    "  Render: <code>publish_template01 --template 01 --title … --subtitle …</code> + upload نشر → النشر الآن\n\n"
    "<b>Commands</b>\n"
    "/start /menu /help — Control Center · /url — wizard · /templates — list · /status — state · /interrupt — cancel · /set_handle {handle} / /set_tiktok {handle} — persists to .env + jobs/handle.json · /logs — jobs.csv\n\n"
    "<b>Files</b>\n"
    "• <code>README.md</code> — run (<code>opencode serve</code> + <code>python bot.py</code>), setup, layout, state machine (this view formats README for Telegram: headers → &lt;b&gt;, code → &lt;pre&gt;/&lt;code&gt;)\n"
    "• <code>bot.py</code> — wizard v2 + pipeline\n"
    "• <code>config.py</code> — env (BOT_TOKEN, ALLOWED_CHAT_ID, WATERFOX_PROFILE, handles via /set_handle)\n"
    "• <code>scripts/tiktok_vertical_fast.py</code> — renderer (one overlay PNG + ffmpeg filter_complex)\n"
    "• <code>jobs/media/*_tiktok.mp4</code> — previews (generated on demand)\n\n"
    "Tap 📄 Send docs as files to get README.md + template spec as documents. Full details: <code>README.md</code> is the source of truth for the app."
)

TEMPLATES_TEXT = (
    "🎨 <b>Templates — list view</b>\n"
    "Tap a template to select it for next URL (or type 00/01 when wizard asks).\n\n"
    "<b>Template 00 — Raw 9:16</b>\n"
    "• Clean vertical 1080x1920, blurred 16:9 fill (gblur sigma=18) + sharp center, <b>no caption card, no burned text</b>\n"
    "• Watermark {handle} top-left (configurable via /set_handle) (unless --no-watermark / no watermark) — watermark only, card is empty\n"
    "• Description → only TikTok post text, never burned into pixels. If empty, post desc empty (+ auto #hashtags)\n"
    "• For clean reposts, no branding overlay. Preview: generated on demand from your video (<code>jobs/media/*_tiktok.mp4</code>)\n"
    "• Render: <code>tiktok_vertical_fast --title \"\" --subtitle \"\"</code> → transparent overlay check\n\n"
    "<b>Template 01 — 9:16 TikTok with Card</b>\n"
    "• Vertical 1080x1920 + Majalla card (0.94 wide, 1.95× tall, rounded 22, shadow, gold accent #EAB308 right edge RTL)\n"
    "• Fonts Majalla Bold 0.052H / Majalla 0.040H via arabic_reshaper+bidi, watermark {handle} top-left (configurable via /set_handle) Segoe UI 0.028 small top-left\n"
    "• Description burned as title/subtitle card AND used as post description (split on “ - ”)\n"
    "• For branded Arabic content. Preview: generated on demand from your video\n"
    "• Render: <code>publish_template01 --template 01 --title … --subtitle …</code> + upload نشر→النشر الآن\n\n"
    "Select below 👇 — bot replies ✅ Template 0x saved."
)

SETTINGS_TEXT = (
    "⚙️ <b>Settings</b>\n"
    "Handles: TikTok <code>{tiktok}</code>  Watermark <code>{watermark}</code>\n"
    "Jobs dir: <code>{jobs_dir}</code>  FFmpeg: <code>{ffmpeg_dir}</code>\n"
    "Cookie check: every {hours}h  Max uploads/day: {max_uploads}\n"
    "Use /set_handle @myhandle or /set_tiktok @myhandle to update (sets both, persists to .env + jobs/handle.json).\n"
    "Commands: /status /interrupt /logs /url /templates"
)

TEMPLATES_EMPTY_NOTE = "No template selected yet — defaults to 00 for next wizard. Tap 00 or 01 above."

# helper to map automation errors to user-facing messages (T7)
def error_message(kind: str, reason: str = "") -> str:
    """Map kind to bilingual user-facing message. kind in: cookie, download, montage, caption, upload, verify."""
    r = reason or "unknown"
    kind = (kind or "").lower()
    if kind == "cookie":
        return COOKIE_EXPIRED
    if kind == "download":
        return DOWNLOAD_FAIL_MSG.format(reason=r)
    if kind == "montage":
        return MONTAGE_FAIL_MSG.format(reason=r)
    if kind == "caption":
        return CAPTION_FAIL_MSG.format(reason=r)
    if kind == "upload":
        return UPLOAD_FAIL_MSG.format(reason=r)
    if kind == "verify":
        return VERIFY_FAILED.format(reason=r)
    return ERROR_GENERIC.format(reason=r)
