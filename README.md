# tg-montage

Telegram → verify URL → download (yt-dlp + Waterfox cookies) → OpenMontage
montage (via `opencode serve`) → writer caption → TikTok upload (Playwright
flight-plan) → result back to Telegram. Cancel at any stage.

## Run (two services, started manually — never spawned by the CLI)

```
Terminal 1:  opencode serve          # the agent brain
Terminal 2:  py .venv\Scripts\activate; python bot.py
```

## Setup

```
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
copy .env.example .env   # then fill BOT_TOKEN
python bot.py --check-config
```

## Tickets

See `docs/TICKETS.md` for the build order. Current: T1 (structure) → T2
(downloader) → T3 (tests) → T4 (OpenMontage) → T5 (template 01) → T6
(approval loop) → T7 (uploader) → T8+ (Telegram features).

## Layout

```
bot.py            entry: long polling / --check-config
config.py         env-driven settings (no secrets in code)
core/             jobs (state machine), verifier, downloader, interrupt
agents/           opencode serve client
upload/           Playwright flight-plan TikTok uploader (T7)
ui/               all Telegram strings + keyboards
jobs/             <id>.job.json state files + downloaded media
tests/            pytest suites (T3+)
```

## State machine

new → verifying → downloading → montaging → writing_caption →
awaiting_approval → uploading → done
(cancel/fail from any state; single job at a time, rest queue)
