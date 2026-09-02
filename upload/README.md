"""Playwright flight-plan TikTok uploader (T7 ports the full spec).

Spec summary (from design sessions):
- calibrate.py records flight_plan.json {name, x, y, w, h, reference_crop}
  at fixed viewport 1366x768, deviceScaleFactor 1
- production: crop-verify before every click, jitter ±2px, human delays
- caption PASTED (clipboard), DOM text verified after paste
- ledger.json idempotency (video sha256), daily cap, exit codes 2/3
"""
