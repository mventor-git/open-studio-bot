# mventor-ticket-001 — tg-montage T1: repo structure

## Status
Validated

## Goal
Scaffold the modular tg-montage repo: full directory tree, config, job store +
state machine, interrupt registry, centralized UI strings, stubs for
downloader (T2), opencode client (T4), uploader (T7), and `bot.py
--check-config` acceptance.

## Scope
- Tree: bot.py, config.py, core/, agents/, upload/, ui/, jobs/, tests/, docs/
- core/jobs.py: atomic JSON job store, state machine constants, platform regex
- core/interrupt.py: flag + subprocess kill registry (thread-safe)
- core/verifier.py + core/downloader.py: contracts + Waterfox cookie helper
- config.py: env-driven (BOT_TOKEN, OPENCODE_SERVER_URL, WATERFOX_PROFILE, caps)
- ui/messages.py + keyboards.py: all strings centralized
- requirements.txt, .env.example, .gitignore, README.md, docs/TICKETS.md

## Acceptance
- `python bot.py --check-config` passes
- module selftests pass (jobs + interrupt invariants)
- no business logic beyond contracts (T2/T4/T7 raise NotImplementedError)

## Validation Notes
- Selftests run with system python (no venv needed for stdlib-only modules)
- check-config verified with and without BOT_TOKEN set

## Known Risks
- Waterfox profile path default may differ per install (env override exists)
- yt-dlp on Windows may need Deno for YouTube (T2 concern, not T1)

## Related Tickets
- OpenMontage pipeline work tracked separately in OpenMontage repo
