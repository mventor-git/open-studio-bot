"""tg-montage configuration.

All settings come from environment / .env (see .env.example).
Never hardcode tokens or profile paths here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# Default title/subtitle: empty — fetched from video URL via yt-dlp probe when not provided (no hardcoded test data)
DEFAULT_TITLE = ""
DEFAULT_SUBTITLE = ""


def _load_dotenv() -> None:
    """Tiny .env loader (no python-dotenv dependency)."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _load_handle_json() -> None:
    """Optional persisted handle override from jobs/handle.json (survives .env edits)."""
    try:
        jf = REPO_ROOT / "jobs" / "handle.json"
        if jf.exists():
            import json as _j
            data = _j.loads(jf.read_text(encoding="utf-8"))
            for k in ("TIKTOK_HANDLE", "WATERMARK_HANDLE"):
                if k in data and data[k]:
                    os.environ.setdefault(k, str(data[k]).strip())
    except Exception:
        pass


_load_dotenv()
_load_handle_json()


@dataclass
class Config:
    # Telegram
    bot_token: str = field(default_factory=lambda: os.environ.get("BOT_TOKEN", ""))
    allowed_chat_id: int = field(
        default_factory=lambda: int((os.environ.get("ALLOWED_CHAT_ID") or "0").strip() or "0")
    )

    # opencode serve
    opencode_server_url: str = field(
        default_factory=lambda: os.environ.get("OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
    )

    # Waterfox (Firefox fork) profile dir for cookie extraction
    waterfox_profile: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "WATERFOX_PROFILE",
                r"C:\Users\Mventor\AppData\Roaming\Waterfox\Profiles",
            )
        )
    )

    # Storage
    jobs_dir: Path = field(default_factory=lambda: REPO_ROOT / "jobs")
    max_uploads_per_day: int = field(
        default_factory=lambda: int((os.environ.get("MAX_UPLOADS_PER_DAY") or "3").strip() or "3")
    )

    # Download limits
    max_resolution: str = field(default_factory=lambda: os.environ.get("MAX_RESOLUTION", "720p"))
    max_duration_seconds: int = field(
        default_factory=lambda: int((os.environ.get("MAX_DURATION_SECONDS") or "600").strip() or "600")
    )

    # Handles — empty until user sets via /set_handle or /set_tiktok; watermark skipped if empty
    tiktok_handle: str = field(default_factory=lambda: (os.environ.get("TIKTOK_HANDLE") or "").strip())
    watermark_handle: str = field(default_factory=lambda: (os.environ.get("WATERMARK_HANDLE") or "").strip())
    cookie_check_hours: int = field(default_factory=lambda: int((os.environ.get("COOKIE_CHECK_HOURS") or "24").strip() or "24"))

    # Default captions — empty (no hardcoded test strings); bot fetches from video URL when skipped
    default_title: str = field(default_factory=lambda: (os.environ.get("DEFAULT_TITLE") or "").strip())
    default_subtitle: str = field(default_factory=lambda: (os.environ.get("DEFAULT_SUBTITLE") or "").strip())

    # Bundled ffmpeg/ffprobe (portable install under tools/)
    ffmpeg_dir: Path = field(default_factory=lambda: REPO_ROOT / "tools" / "ffmpeg-9.0.1-essentials_build" / "bin")

    def ensure_dirs(self) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)


config = Config()


def check_config() -> list[str]:
    """Return a list of human-readable problems; empty list = OK."""
    problems: list[str] = []
    if not config.bot_token:
        problems.append("BOT_TOKEN is not set (Telegram bot will not start)")
    if config.allowed_chat_id <= 0:
        problems.append("ALLOWED_CHAT_ID is not set (bot would answer anyone)")
    # handles intentionally not required here — bot prompts via /set_handle /set_tiktok if empty
    if not (config.ffmpeg_dir / "ffprobe.exe").exists():
        problems.append(f"ffprobe not found in {config.ffmpeg_dir} (audio check will fail)")
    if not config.waterfox_profile.exists():
        problems.append(f"WATERFOX_PROFILE not found: {config.waterfox_profile}")
    try:
        config.ensure_dirs()
    except OSError as exc:
        problems.append(f"cannot create jobs dir {config.jobs_dir}: {exc}")
    return problems


def _normalize_handle(handle: str) -> str:
    h = (handle or "").strip()
    if not h:
        return ""
    if not h.startswith("@"):
        h = "@" + h.lstrip("@")
    return h


def _update_env_file(key: str, value: str) -> None:
    env_file = REPO_ROOT / ".env"
    lines: list[str] = []
    found = False
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        k, _, _ = line.partition("=")
        if k.strip() == key:
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def persist_handle(handle: str) -> str:
    """Persist new handle to .env + jobs/handle.json and update live config.
    Returns normalized handle."""
    norm = _normalize_handle(handle)
    if not norm:
        raise ValueError("handle required, e.g. @handle")
    # update live config + env
    config.tiktok_handle = norm
    config.watermark_handle = norm
    os.environ["TIKTOK_HANDLE"] = norm
    os.environ["WATERMARK_HANDLE"] = norm
    try:
        _update_env_file("TIKTOK_HANDLE", norm)
        _update_env_file("WATERMARK_HANDLE", norm)
    except Exception:
        pass
    # also persist to jobs/handle.json (always, cheap fallback)
    try:
        import json as _j
        jf = REPO_ROOT / "jobs" / "handle.json"
        jf.parent.mkdir(parents=True, exist_ok=True)
        jf.write_text(_j.dumps({"TIKTOK_HANDLE": norm, "WATERMARK_HANDLE": norm}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return norm
