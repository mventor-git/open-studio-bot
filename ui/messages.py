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
