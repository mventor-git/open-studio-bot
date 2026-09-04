"""All user-visible Telegram strings live here (single source, easy to tune)."""


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
    "🎛️ <b>Control Center</b> — tg-montage\n"
    "Pick an action:\n"
    "• 📚 Docs — file list + docs summary (TICKETS, templates)\n"
    "• ❓ Help — step-by-step wizard + button guide\n"
    "• 🎨 Templates — list view, tap to select 00 / 01\n"
    "• 📊 Logs — jobs.csv (Excel-ready)\n"
    "• ⚙️ Settings — handles, status, config\n"
    "• 🔗 Send URL — start wizard (/url or paste link)\n\n"
    "Tip: /start /menu /help anytime returns here."
)

HELP_TEXT = (
    "❓ <b>Help — How to use tg-montage</b>\n\n"
    "<b>Step-by-step wizard (v2):</b>\n"
    "1️⃣ <b>Send URL</b> — via /url or paste link (YouTube / TikTok / IG / FB).\n"
    "   Optional cut in same message: <code>Cut 0.25 to 1.00</code> or <code>0:25 to 1:00</code> or <code>26:19 to 27:10</code>.\n"
    "   Bot verifies: must contain video & be downloadable (yt-dlp probe). Else: “Invalid or not downloadable”.\n"
    "2️⃣ <b>Select template</b> — 00 or 01 (empty → 00):\n"
    "   • 00 Raw 9:16 — clean vertical (1080x1920, blurred fill, no card, no burned text) — for clean reposts\n"
    "   • 01 TikTok Card — 9:16 + Majalla card (0.94w × 1.95h, gold #EAB308) + Arabic shaping + @mventor watermark top-left — for branded AR\n"
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
    "<code>/set_handle @mventor</code> / <code>/set_tiktok @mventor</code> → sets watermark + TikTok handle\n"
)

DOCS_TEXT = (
    "📚 <b>Docs — tg-montage</b>\n\n"
    "<b>Summary (from docs/TICKETS.md + docs/templates/01-vertical-9x16.md):</b>\n"
    "Pipeline: Telegram → verify URL (yt-dlp dump-json + Waterfox cookies) → download (--download-sections) → montage (vertical_fast 1080x1920) → preview [Accept/Rerun/Reject] → upload (Playwright النشر→النشر الآن, scroll fix y1488) → Done. State: new→verifying→downloading→montaging→awaiting_approval→uploading→done.\n\n"
    "<b>File list:</b>\n"
    "• <code>docs/TICKETS.md</code> — build order T1→T7+, acceptance per ticket, contracts source of truth\n"
    "• <code>docs/templates/01-vertical-9x16.md</code> — Template 00/01 spec (1080x1920, blur sigma18, Majalla card 0.94×1.95, gold #EAB308, @mventor top-left Segoe UI 0.032), renderer <code>scripts/tiktok_vertical_fast.py</code> (one overlay PNG + ffmpeg filter_complex), publisher <code>scripts/publish_template01.py --template 00|01</code>, two-step publish + POST /web/project/post/v1/ 200\n"
    "• <code>docs/tickets/mventor-ticket-001.md</code> — T1 scaffold (jobs/store, interrupt, ui)\n"
    "• <code>README.md</code> — run (<code>opencode serve</code> + <code>python bot.py</code>), setup, layout, state machine\n"
    "• <code>bot.py</code> — wizard v2 flow (verify→thumb→template 00 default→random 30s→desc/hashtags→preview confirm/rerun/revert + Use Last/New URL)\n"
    "• <code>config.py</code> — env-driven (BOT_TOKEN, ALLOWED_CHAT_ID, WATERFOX_PROFILE, TIKTOK_HANDLE/WATERMARK_HANDLE, ffmpeg dir)\n"
    "• <code>core/jobs.py</code> — atomic JSON store, platform regex, ACTIVE_STATES includes awaiting_approval\n"
    "• <code>core/verifier.py</code> / <code>core/downloader.py</code> — probe + download\n"
    "• <code>scripts/tiktok_vertical_fast.py</code> + <code>scripts/caption_card.py</code> — card + handle\n"
    "• <code>jobs/media/test_00.mp4</code> vs <code>jobs/media/qaid_tiktok.mp4</code> — preview samples for 00 (clean) vs 01 (card)\n\n"
    "Local docs are under <code>docs/</code> — bot can send them as documents on tap."
)

TEMPLATES_TEXT = (
    "🎨 <b>Templates — list view</b>\n"
    "Tap a template to select it for next URL (or type 00/01 when wizard asks).\n\n"
    "<b>Template 00 — Raw 9:16</b>\n"
    "• Clean vertical 1080x1920, blurred 16:9 fill (gblur sigma=18) + sharp center, <b>no caption card, no burned text</b>\n"
    "• Watermark @mventor top-left (unless --no-watermark / no watermark) — watermark only, card is empty\n"
    "• Description → only TikTok post text, never burned into pixels. If empty, post desc empty (+ auto #hashtags)\n"
    "• For clean reposts, no branding overlay. Preview: <code>jobs/media/test_00.mp4</code>\n"
    "• Render: <code>tiktok_vertical_fast --title \"\" --subtitle \"\"</code> → transparent overlay check\n\n"
    "<b>Template 01 — 9:16 TikTok with Card</b>\n"
    "• Vertical 1080x1920 + Majalla card (0.94 wide, 1.95× tall, rounded 22, shadow, gold accent #EAB308 right edge RTL)\n"
    "• Fonts Majalla Bold 0.052H / Majalla 0.040H via arabic_reshaper+bidi, @mventor watermark Segoe UI 0.028 small top-left\n"
    "• Description burned as title/subtitle card AND used as post description (split on “ - ”)\n"
    "• For branded Arabic content. Preview: <code>jobs/media/qaid_tiktok.mp4</code> / <code>qaid_seg_tiktok.mp4</code>\n"
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
