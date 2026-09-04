# Open Studio Bot

A Telegram-powered, self-hosted automation suite for video montage, template editing, and TikTok publishing — built by **Mventor**.

## Overview

Open Studio Bot connects Telegram to two background services:

- **opencode serve** — the agent brain for building, editing, and orchestrating montages via OpenStudio’s pipeline tools.
- **Telegram bot** — wizard-driven: verify YouTube/Instagram/Facebook/TikTok video → cut to 30s → generate template (00 or 01) → preview → publish to TikTok.

All configuration lives in `.env`; no secrets or credentials are hardcoded into the repository.

## System layout

```
open-studio-bot/
├── .venv/                 # Python virtual env (managed by `.venv/Scripts/activate`)
├── .env                   # Bot credentials, handles, Waterfox path (gitignored)
├── .gitignore             # cleanup of artifacts, logs, and pycache
├── bot.py                 # Telegram bot core (Wizard v2, approval loop)
├── config.py              # Python dataclasses for env-driven settings
├── core/                  # jobs (state machine, verifier, downloader, interrupt registry)
├── gui_config.py          # retro-styled 8-bit GUI to set .env, Waterfox, templates, and check deps
├── scripts/               # production scripts (dispatcher, caption card, TikTok upload)
├── tests/                 # automated anti‑regressions and full Wizard flow (e.g., `test_approval.py`)
├── docs/                  # external docs (TICKETS.md, 01-vertical‑9x16.md)
├── agents/                # opencode serve client (for automatic montage agents)
├── upload/                # helper README (auto‑generated)
├── run_forever.bat         # launcher for both services (opencode + bot)
├── run_opencode_forever.bat
├── run_bot_forever.bat
└── requirements.txt       # core Python dependencies
```

## Getting started

### Prerequisites

- Windows 10/11 (PowerShell / Command Prompt)
- Python 3.9+
- 8‑core CPU for video processing (ffmpeg), stable internet, and:

### Installation (one‑time)

1. **Open the repo root in a terminal** (`cd "C:\Users\Mventor\open-studio-bot"`).
2. **Create a virtual environment** (comes pre‑made in the repo if you have opencode installed):

```powershell
py -3 -m venv .venv
.venv\Scripts\activate
```
3. **Install dependencies**

```powershell
pip install -r requirements.txt
playwright install chromium
```
4. **Set up the .env file**

Copy from `.env.example` and fill:

```text
BOT_TOKEN=123456789:YOUR_TOKEN_HERE
ALLOWED_CHAT_ID=7830528991

# Optional handles (will prompt via /set_handle if empty)
TIKTOK_HANDLE=@videosforall19      # target TikTok account
WATERMARK_HANDLE=@mventor        # watermark on Template 01 (empty to skip)

# If you don’t want the default profile, give a custom Waterfox path
# WATERFOX_PROFILE=C:\Users\Mventor\AppData\Roaming\Waterfox\Profiles
```

### Running the services

Open two separate terminal windows (or PowerShell sessions). **DO NOT start the bot in the same session where you ran the installation.**

**Terminal 1 (Opencode)**

```powershell
# In the repo root, with .venv activated
start-process "run_opencode_forever.bat"
```

**Terminal 2 (Telegram Bot)**

```powershell
start-process "run_bot_forever.bat"
```

Both start a background service that self‑restarts on crash. To stop:

```powershell
taskkill /FI "WINDOWTITLE eq osb-*"
```

### Bot commands (Telegram)

All commands assume you have added the bot to a group/channel where the chat ID matches `ALLOWED_CHAT_ID`.

- `/start` – Open the Control Center (docs, help, templates, settings, send a URL, logs).
- `/url <link>` – Submit a video link (YouTube, Instagram Reel, Facebook share, TikTok).
- `/status` – Current wizard step and job state.
- `/interrupt` – Cancel the current preview (returns to ready for a new URL).
- `/logs` – Download `jobs.csv` (UTF‑8‑BOM, Arabic preserved).
- `/set_handle @yourhandle` – Sets TikTok and watermark handles (both at once).
- `/help` – In‑app guide (six steps).

### Quick usage example

1. **Start the wizard**

```
/start
```

2. **Choose a video**

```
/url https://www.youtube.com/watch?v=123abc
```

3. **Select template (00 or 01)** – Bot will show a preview and ask for a cut (send e.g. `Cut 0.25 to 1.00` or `/skip` for random 30‑second slice).

4. **Provide optional description / hashtags**

5. **Review the preview** – Tap the `[✅ Confirm to Upload]` button.

6. **Post to TikTok** – Waterfox cookie login is required for private videos. Successful uploads are shown as links inside the preview caption.

### Template 00 vs Template 01

- **Template 00** – Clean 9:16 video, optional watermark, no burned text.
- **Template 01** – 9:16 vertical + a styled Majalla card (9:16 tall, 0.94 wide) + watermark handle if set + gold accent.

### Errors & troubleshooting

- **“❌ TikTok session expired — please re‑login in Waterfox”** → Ensure your TikTok account (`TIKTOK_HANDLE`) is set and Waterfox has that login.
- **“Invalid or not downloadable”** → Must be a supported platform (YouTube, Instagram, Facebook, TikTok) or a Waterfox‑protected video.
- **“No pending preview”** → Send a new URL (`/url` or paste).

### Updating the repository

Git operations respect the `/ponytail` principle (laziness, minimal code, clean edits). All commits carry a concise, descriptive message.

### Credits

Built by **Mventor** agents:

- **Muse** — project identity, Wizards `muse-ticket-` tickets, profile management.
- **Plan** — high‑level plan.
- **Build** — implementation (T7, T8+).
- **General** — research, exploration, modular decomposition.
- **Explore** — repository mapping, impact analysis.

#### Core technologies referenced from other agents

- **Muse** — `profile.md`, `tickets/` for project context.
- **Plan** — abstract high‑level planning and orchestration.
- **General** — research, analysis, and general-purpose tooling.
- **Build** — implementation, heavy integration work.
- **Explore** — repository discovery, searching, and code mapping.
- **Webapp‑testing** — Playwright integration tests for TikTok Studio UI.

#### Third‑party tools

- **OpenMontage** — development‑time pipeline; runtime uses the same installer (`pip install -r requirements.txt`).
- **opencode serve** — LangChain‑style agent endpoint for building montages.
- **opencode** — The Free Language Model, used by opencode serve.

OpenStudio Bot reimplements the core logic for YouTube/Instagram/Facebook/TikTok video verification, Waterfox cookie handling, and fast 9:16 vertical montage.

### License

Unlicensed for development. For internal or community use.

### Support

GitHub issues are tracked via the `mventor‑git` organization; contributions are welcome following the Mventor workflow.