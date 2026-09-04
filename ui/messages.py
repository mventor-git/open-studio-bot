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
    "Select template no. — 00 (raw, no card) or 01 (9:16 + card + @mventor) — "
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
