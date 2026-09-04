# tg-montage — Tickets

Execution order. One ticket per session; each ends with its acceptance test green.

| # | Ticket | Scope | Acceptance |
|---|--------|-------|-----------|
| T1 | Repo structure | Full tree, config, job store + state machine, interrupt registry, messages/keyboards, stubs for T2/T4/T7, `--check-config` | `python bot.py --check-config` passes; selftests pass; no business logic |
| T2 | Downloader function | verifier probe (yt-dlp dump-json + Waterfox cookie fallback), killable download subprocess, ffprobe stream check | CLI verifies + downloads real YT + FB link, reports video/sound |
| T3 | Downloader tests | pytest: 1 link/platform, cookie fallback, interrupt-during-download cleanup, bad URL error | all pass; no orphan yt-dlp processes |
| T4 | OpenMontage test | opencode_client against `opencode serve`: session → mini montage job → result | mini montage mp4 produced from downloaded clip |
| T5 | Template 01 | `01-captions-animations.yaml` (Remotion runtime, word-level captions, animated intro/outro/transitions) + writer agent + caption.txt contract | rendered mp4 shows animated captions; writer output valid |
| T6 | Approval loop | Telegram preview with Accept/Rerun/Cancel; rerun carries user tweak; decision logged | full Telegram round-trip |
| T7 | TikTok uploader | flight-plan Playwright uploader: calibrate, crop verify, paste caption, ledger, daily cap, exit codes 2/3 | 3 clean headless replays + real post |
| T7b | Template 01 publisher | 1080×1920 vertical (blurred fill+sharp center), card 0.94w 1.95×h Majalla, @mventor top-left Segoe UI 0.032, `publish_template01.py` single command + two-step publish `نشر→النشر الآن` confirm modal auto-handled (scroll fix y1488>1080, POST /web/project/post/v1/ 200) | `python scripts/publish_template01.py --source 16:9.mp4 --dry-run` verifies 1080×1920 + modal code present; retry6 POST 200 project_id 7681631937933661205 |
| T8+ | Telegram features | 1 /status+/interrupt everywhere · 2 job queue · 3 error taxonomy · 4 Route A raw video · 5 scheduled drops · 6 templates 02/03 · 7 VL keyframes · 8 more platforms | each its own green ticket |

## Working agreement
- Tickets in order; a red ticket blocks the next.
- Each ticket ends with a one-line report (e.g. `T3 ✅ 9/9 tests, no orphans`).
- Design contracts live in this file + module docstrings — the source of truth.
