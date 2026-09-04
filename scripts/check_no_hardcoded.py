#!/usr/bin/env python
"""Pre-commit/CI check: fail if hardcoded test data or credentials leak into production code.

Usage: python scripts/check_no_hardcoded.py
Exit 0 = clean, 1 = blocked (hardcoded found).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO = Path(__file__).resolve().parents[1]

# Patterns that must NOT appear in production code (allow only in git history / jobs/*.job.json fixtures)
FORBIDDEN = [
    "test_00",
]

# Credential / handle patterns (exact handles, not placeholders)
# We allow {handle} placeholder but not literal @mventor/@videosforall19 etc in code
HARDCODED_HANDLES = ["@mventor", "@videosforall19"]
# Raw token pattern (bot token format)
RAW_TOKEN_RE = re.compile(r"\b\d{7,10}:[A-Za-z0-9_-]{30,}\b")
# Assignment literal for BOT_TOKEN with long string
TOKEN_ASSIGN_RE = re.compile(r'BOT_TOKEN\s*=\s*["\'][A-Za-z0-9:_\-]{20,}["\']')
CHAT_ASSIGN_RE = re.compile(r'ALLOWED_CHAT_ID\s*=\s*["\']?\d{5,}["\']?')


def check_file(path: Path) -> list[str]:
    # ponytail: this file itself contains the forbidden strings as its check list — skip self
    if path.resolve() == (REPO / "scripts" / "check_no_hardcoded.py").resolve():
        return []
    errs: list[str] = []
    try:
        txt = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return [f"{path}: cannot read ({e})"]
    for pat in FORBIDDEN:
        if pat in txt:
            for i, line in enumerate(txt.splitlines(), 1):
                if pat in line and not line.strip().startswith("#"):
                    # allow comment lines that are inside check_no_hardcoded.py's own list? already skipped file
                    errs.append(f"{path.relative_to(REPO)}:{i} forbidden {pat!r}: {line.strip()[:140]}")
    # handle hardcoding in messages/templates only: allow comment but not code
    for h in HARDCODED_HANDLES:
        if h in txt:
            for i, line in enumerate(txt.splitlines(), 1):
                if h in line:
                    # allow if file is publish_template01 and handle is in log? still block; but spec says TEMPLATES_TEXT should use {handle}
                    # So any production code containing literal handle is block
                    # Exception: .env, jobs/handle.json, logs are not scanned
                    errs.append(f"{path.relative_to(REPO)}:{i} hardcoded handle {h!r}: {line.strip()[:140]}")
    # token literals (ignore lines that use os.environ)
    for i, line in enumerate(txt.splitlines(), 1):
        if "os.environ" in line:
            continue
        if TOKEN_ASSIGN_RE.search(line):
            errs.append(f"{path.relative_to(REPO)}:{i} hardcoded BOT_TOKEN assignment: {line.strip()[:140]}")
        if RAW_TOKEN_RE.search(line) and "example" not in line.lower():
            if not line.strip().startswith("#"):
                errs.append(f"{path.relative_to(REPO)}:{i} raw BOT_TOKEN pattern: {line.strip()[:140]}")
        # chat id literal (only flag if assignment without environ)
        if CHAT_ASSIGN_RE.search(line) and "os.environ" not in line:
            errs.append(f"{path.relative_to(REPO)}:{i} hardcoded ALLOWED_CHAT_ID: {line.strip()[:140]}")
    # caption_card height check: ensure not doubled
    if path.name == "caption_card.py":
        for i, line in enumerate(txt.splitlines(), 1):
            code = line.split("#", 1)[0]
            if "card_h" in code and re.search(r"\*\s*1\.95", code):
                errs.append(f"{path.relative_to(REPO)}:{i} card_h doubled (base_h * 1.95) should be base_h + 8: {line.strip()[:140]}")
    return errs


def main() -> int:
    prod_files: list[Path] = []
    prod_files.append(REPO / "bot.py")
    prod_files.append(REPO / "config.py")
    prod_files.append(REPO / "gui_config.py")
    prod_files.extend((REPO / "scripts").glob("*.py"))
    prod_files.extend((REPO / "ui").glob("*.py"))
    prod_files.extend((REPO / "core").glob("*.py"))
    # filter existing
    prod_files = [p for p in prod_files if p.exists()]
    all_errs: list[str] = []
    for p in prod_files:
        all_errs.extend(check_file(p))
    # also check .env.example placeholders are empty
    env_ex = REPO / ".env.example"
    if env_ex.exists():
        txt = env_ex.read_text(encoding="utf-8", errors="ignore")
        for key in ["BOT_TOKEN", "ALLOWED_CHAT_ID", "TIKTOK_HANDLE", "WATERMARK_HANDLE"]:
            m = re.search(rf"^{key}[ \t]*=[ \t]*(.*)$", txt, re.M)
            if m and m.group(1).strip() != "":
                all_errs.append(f".env.example:{key} should be empty placeholder, got {m.group(1)!r}")
        if re.search(r"\d{7,10}:[A-Za-z0-9_-]{30,}", txt):
            all_errs.append(".env.example contains raw token")
    if all_errs:
        print("FAIL check_no_hardcoded — hardcoded test data / credentials found:", file=sys.stderr)
        for e in all_errs:
            print(f"  - {e}", file=sys.stderr)
        print("\nFix: remove hardcoded test data, use config.watermark_handle / env placeholders, ensure card_h = base_h + 8", file=sys.stderr)
        return 1
    print("OK check_no_hardcoded — no hardcoded test data or credentials in production code")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
