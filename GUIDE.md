# Open Studio Bot — User Guide

This guide walks you through every step of using Open Studio Bot from install to publishing your first TikTok.

---

## 1. One‑time installation

**Requirements**
- Windows 10/11
- Python 3.9+ (tested on 3.11)
- Internet connection (for yt-dlp, Playwright, and TikTok API)

**Steps**

1. **Clone the repo**

   ```powershell
   git clone https://github.com/mventor-git/open-studio-bot.git
   cd open-studio-bot
   ```

2. **Create the virtual environment**

   ```powershell
   py -3 -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies**

   ```powershell
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Configure `.env`**

   Copy the example file and fill in your values:

   ```powershell
   copy .env.example .env
   ```

   Open `.env` in a text editor and set:

   ```text
   BOT_TOKEN=123456789:YOUR_BOT_TOKEN_HERE      # from @BotFather
   ALLOWED_CHAT_ID=123456789                    # your Telegram chat/user ID

   # Optional — the bot will prompt you if these are empty
   TIKTOK_HANDLE=@your_tiktok_account           # where videos get published
   WATERMARK_HANDLE=@your_watermark             # burned onto Template 01 (empty = skip)

   # Optional — only change if your Waterfox profile isn't in the default location
   # WATERFOX_PROFILE=C:\Users\YourName\AppData\Roaming\Waterfox\Profiles
   ```

   **Where to get BOT_TOKEN & CHAT_ID:**
   - Create a bot with Telegram’s @BotFather → `/newbot` → copy the token.
   - To find your `ALLOWED_CHAT_ID`, send a message to your bot, then visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` and look for `"chat":{"id":123456789}`.

5. **Test the config**

   ```powershell
   .venv\Scripts\python.exe bot.py --dry-run
   ```

   You should see `dry-run PASS`.

---

## 2. Running the two services

Open **two separate terminal windows** (or PowerShell sessions). Do **not** start both in the same window — they run forever and block.

### Terminal 1 — Opencode serve (montage brain)

```powershell
start-process "run_opencode_forever.bat"
```

This launches `opencode serve --port 4096` and restarts it automatically if it crashes. Leave this window open.

### Terminal 2 — Telegram bot

```powershell
start-process "run_bot_forever.bat"
```

This launches the Telegram wizard and restarts on crash. Leave this window open.

> **To stop both cleanly:**
> ```powershell
> taskkill /FI "WINDOWTITLE eq osb-*"
> ```

---

## 3. Using the bot (Telegram)

Open Telegram, start a chat with your bot, and send:

```
/start
```

You’ll see the **Control Center** — an inline keyboard with:

| Button | Action |
|--------|--------|
| 📚 Docs | README summary + links |
| ❓ Help | Step‑by‑step guide + button legend |
| 🎨 Templates | Template 00 (clean) vs 01 (card) — tap to select |
| 📊 Logs | Download `jobs.csv` (Excel‑ready, Arabic‑safe) |
| ⚙️ Settings | Current handles, paths, limits |
| 🔗 Send URL | Starts the wizard — send a video link next |

---

## 4. The Wizard — step by step

### Step 1 — Send a video URL

Paste any of these formats:

- YouTube: `https://www.youtube.com/watch?v=ABC123` or `https://youtu.be/ABC123`
- Instagram Reel: `https://www.instagram.com/reel/XYZ789/`
- Facebook share: `https://www.facebook.com/share/r/18eW1s6Z2t/`
- TikTok: `https://www.tiktok.com/@user/video/123456789`

The bot verifies the URL (checks downloadability via yt‑dlp and Waterfox cookies for private videos).

### Step 2 — Choose template

```
Select template no. — 00 (raw) or 01 (card) — type 00 or 01 or nothing (default 00)
```

- **00** = clean 9:16 vertical, no burned text, optional watermark.
- **01** = 9:16 + Majalla card (Arabic shaping) + watermark handle if set.

Send `00` or `01` (or just press enter for `00`).

### Step 3 — Cut selection

```
Select cut 00:00 to 00:00 (video is 00:00–19:05)
```

Options:
- **Explicit cut**: `Cut 0.25 to 1.00` (25s–60s), `0:25 to 1:00`, `26:19 to 27:10`
- **Random 30s**: Send `/skip`, `skip`, `random`, `nothing`, or leave blank.
- **Full video**: If shorter than 30s, the whole video is used.

### Step 4 — Description (optional)

```
Type Description (or skip — I'll take it from the video URL itself)
```

- **Type your own** (Arabic, English, mixed, emojis).
- **Skip**: send `/skip` or press enter — the bot uses the video’s title from yt‑dlp.

### Step 5 — Hashtags (optional, unlimited)

```
Type Hashtags (e.g., تاريخ حضارة — I'll add #)
```

- With or without `#` — bot normalises to `#تاريخ #حضارة`.
- Unlimited count; Arabic, English, mixed.
- Send `/skip` or press enter for none.

### Step 6 — Preview + action

The bot sends the montage as a video preview with three inline buttons:

| Button | Action |
|--------|--------|
| ✅ Confirm to Upload | Publishes to TikTok (uses Waterfox cookies, handles Joyride, confirm modal). |
| 🔁 Rerun | Ask for new description/hashtags → re‑render + new preview. |
| ❌ Revert | Cancel; bot asks **Use Last URL** or **New URL**. |

After confirm, you’ll see:

```
✅ Posted — https://www.tiktok.com/@yourhandle/video/123456789
```

---

## 4. Managing Waterfox cookies (crucial for private/TikTok videos)

The bot uses **Waterfox** (a Firefox fork) to extract login cookies for private Instagram/Facebook/TikTok videos and for the TikTok Studio upload step.

1. **Install Waterfox** (https://www.waterfox.net/).
2. **Log in to TikTok** in Waterfox: open `https://www.tiktok.com`, log in with your account (`TIKTOK_HANDLE`).
3. **Verify**: in the bot’s Control Center → ⚙️ Settings → you should see your handle.
4. **Daily check**: the bot verifies cookies every 24h (configurable via `COOKIE_CHECK_HOURS` in `.env`).
5. **If cookies expire**: you’ll get `❌ TikTok session expired — please re‑login in Waterfox at tiktok.com then send /retry`.

---

## 5. CLI tools

### Retro Config GUI

```powershell
.venv\Scripts\python.exe gui_config.py
```

- Game Boy 8‑bit themed window (custom title bar, pixel buttons).
- Fields for BOT_TOKEN, CHAT_ID, TIKTOK_HANDLE, WATERMARK_HANDLE, Waterfox profile.
- Template checkboxes (00 / 01).
- **VERIFY** Waterfox cookies button (shows count + session status).
- **CHECK DEPS** installs missing Python packages + Playwright chromium + ffmpeg (for clean Windows).

### Dry‑run health check

```powershell
.venv\Scripts\python.exe bot.py --dry-run
```

- Validates parsing, wizard flow, callbacks, keyboards — no Telegram network call.

### Tests

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
```

Runs:
- `test_01_core_jobs.py` — platform detection, job state machine, interrupt registry.
- `test_02_downloader.py` — yt‑dlp verification, download, ffprobe.
- `test_03_approval_flow.py` — approve/rerun/revert/cancel state machine.
- `test_04_regression.py` — Arabic glyphs, card height, confirm button, caption encoding, hardcoded test data, watermark handle config.
- `test_05_no_hardcoded_creds.py` — empty defaults, .env.example placeholders.

---

## 6. Logs & debugging

- `logs/jobs.csv` — UTF‑8‑BOM, one row per finished job (timestamp, URL, template, cut, description, hashtags, state, TikTok URL, error). Open in Excel → Arabic renders correctly.
- `logs/callback.log` — every callback (approve, confirm, rerun, reject, use_last, new_url, cancel).
- `/logs` command in Telegram → downloads the CSV.

---

## 7. Troubleshooting quick‑reference

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Conflict: terminated by other getUpdates` | Two bot instances polling | `taskkill /FI "WINDOWTITLE eq osb-*"` then restart |
| `❌ TikTok session expired` | Waterfox cookies stale | Re‑login in Waterfox → `/retry` |
| `Invalid or not downloadable` | Unsupported link or private without cookies | Check platform, ensure Waterfox login |
| `Preview send failed: Timed out` | 5 MB video too slow for default timeout | Bot retries once with 60s timeout (fixed in T8) |
| `Job not awaiting approval` | Old preview from previous session | Send `/start` → new URL |
| `No pending preview` | Bot restart cleared in‑memory wizard | Send a new URL |

---

## 8. Folder layout (what to ignore)

The following are **gitignored** (never committed):

- `.env` — your secrets
- `.venv/` — virtual environment
- `jobs/` — runtime job JSON + media (handle.json created at runtime)
- `logs/` — CSV + callback.log + bot.lock
- `screenshots/` — upload screenshots (auto‑created)
- `tools/` — ffmpeg binary (80 MB, download on fresh clone)
- `tests/media/`, `tests/__pycache__/`, `.pytest_cache/`

Everything else is tracked and portable.

---

## 9. Upgrading / re‑cloning

```powershell
cd .. && rm -r open-studio-bot
git clone https://github.com/mventor-git/open-studio-bot.git
cd open-studio-bot
# repeat step 1–4 of installation
```

---

## 10. Support & contributing

- Bugs / feature requests → GitHub Issues on `mventor-git/open-studio-bot`.
- Follow the Mventor workflow: one ticket per change, minimal code, dry‑run green before commit.
- This project was developed with **Mventor** orchestration (agents Muse, Plan, Build, General, Explore) and the **opencode** agent platform.
- Core video pipeline inspired by **OpenMontage** (OpenMontage repo — runtime uses the same dependency list).