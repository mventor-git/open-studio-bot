"""tg-montage configuration.

All settings come from environment / .env (see .env.example).
Never hardcode tokens or profile paths here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


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


_load_dotenv()


@dataclass
class Config:
    # Telegram
    bot_token: str = field(default_factory=lambda: os.environ.get("BOT_TOKEN", ""))

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
        default_factory=lambda: int(os.environ.get("MAX_UPLOADS_PER_DAY", "3"))
    )

    # Download limits
    max_resolution: str = field(default_factory=lambda: os.environ.get("MAX_RESOLUTION", "720p"))
    max_duration_seconds: int = field(
        default_factory=lambda: int(os.environ.get("MAX_DURATION_SECONDS", "600"))
    )

    def ensure_dirs(self) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)


config = Config()


def check_config() -> list[str]:
    """Return a list of human-readable problems; empty list = OK."""
    problems: list[str] = []
    if not config.bot_token:
        problems.append("BOT_TOKEN is not set (Telegram bot will not start)")
    if not config.waterfox_profile.exists():
        problems.append(f"WATERFOX_PROFILE not found: {config.waterfox_profile}")
    try:
        config.ensure_dirs()
    except OSError as exc:
        problems.append(f"cannot create jobs dir {config.jobs_dir}: {exc}")
    return problems
