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
