"""Check no hardcoded credentials — BOT_TOKEN, chat ID, handles."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def test_config_defaults_not_hardcoded():
    txt = (REPO / "config.py").read_text(encoding="utf-8")
    # tiktok_handle and watermark_handle should default to env empty, not literal handle
    assert "videosforall" not in txt.lower(), "config.py should not hardcode tiktok handle"
    assert "@mventor" not in txt, "config.py should not hardcode watermark handle"
    # Check dataclass defaults use os.environ.get with "" fallback
    assert 'os.environ.get("TIKTOK_HANDLE"' in txt, "tiktok_handle should use env"
    assert 'os.environ.get("WATERMARK_HANDLE"' in txt, "watermark_handle should use env"
    assert 'os.environ.get("BOT_TOKEN"' in txt
    # DEFAULT_TITLE/SUBTITLE should be empty
    assert 'DEFAULT_TITLE = ""' in txt
    assert 'DEFAULT_SUBTITLE = ""' in txt
    # Ensure no literal token
    assert not re.search(r'BOT_TOKEN\s*=\s*["\'][A-Za-z0-9:_\-]{20,}["\']', txt), "hardcoded BOT_TOKEN in config.py"


def test_env_example_placeholders():
    txt = (REPO / ".env.example").read_text(encoding="utf-8")
    # BOT_TOKEN should be empty placeholder — use [ \t] not \s to avoid consuming newline
    m = re.search(r"^BOT_TOKEN[ \t]*=[ \t]*(.*)$", txt, re.M)
    assert m, "BOT_TOKEN line missing in .env.example"
    assert m.group(1).strip() == "", f"BOT_TOKEN should be empty placeholder, got {m.group(1)!r}"
    m = re.search(r"^ALLOWED_CHAT_ID[ \t]*=[ \t]*(.*)$", txt, re.M)
    assert m
    assert m.group(1).strip() == "", f"ALLOWED_CHAT_ID should be empty, got {m.group(1)!r}"
    m = re.search(r"^TIKTOK_HANDLE[ \t]*=[ \t]*(.*)$", txt, re.M)
    assert m
    assert m.group(1).strip() == "", f"TIKTOK_HANDLE should be empty, got {m.group(1)!r}"
    m = re.search(r"^WATERMARK_HANDLE[ \t]*=[ \t]*(.*)$", txt, re.M)
    assert m
    assert m.group(1).strip() == "", f"WATERMARK_HANDLE should be empty, got {m.group(1)!r}"
    m = re.search(r"^DEFAULT_TITLE[ \t]*=[ \t]*(.*)$", txt, re.M)
    if m:
        assert m.group(1).strip() == ""
    m = re.search(r"^DEFAULT_SUBTITLE[ \t]*=[ \t]*(.*)$", txt, re.M)
    if m:
        assert m.group(1).strip() == ""


def test_no_hardcoded_token_or_chat_id_in_prod_code():
    prod_files = []
    prod_files.append(REPO / "bot.py")
    prod_files.append(REPO / "config.py")
    prod_files.extend((REPO / "scripts").glob("*.py"))
    prod_files.extend((REPO / "ui").glob("*.py"))
    prod_files.append(REPO / "gui_config.py")
    token_pat = re.compile(r'BOT_TOKEN\s*=\s*["\'][A-Za-z0-9:_\-]{20,}["\']')
    # chat id literal assignment without os.environ (e.g., ALLOWED_CHAT_ID = 7830528991)
    chat_pat = re.compile(r'ALLOWED_CHAT_ID\s*=\s*["\']?\d{5,}["\']?')
    hits = []
    for f in prod_files:
        if not f.exists():
            continue
        txt = f.read_text(encoding="utf-8", errors="ignore")
        for pat, name in [(token_pat, "BOT_TOKEN literal"), (chat_pat, "ALLOWED_CHAT_ID literal")]:
            for i, line in enumerate(txt.splitlines(), 1):
                if "os.environ" in line:
                    continue
                if pat.search(line):
                    # allow if line is in comment? still consider hit
                    if line.strip().startswith("#"):
                        continue
                    hits.append(f"{f.relative_to(REPO)}:{i} {name}: {line.strip()[:120]}")
        # also check for raw token pattern like 8925517685:AA... (typical bot token format digits:letters)
        raw_token_pat = re.compile(r"\b\d{7,10}:[A-Za-z0-9_-]{30,}\b")
        for i, line in enumerate(txt.splitlines(), 1):
            if raw_token_pat.search(line) and "example" not in line.lower():
                if line.strip().startswith("#"):
                    continue
                # ensure not in .env.example handling
                hits.append(f"{f.relative_to(REPO)}:{i} raw BOT_TOKEN: {line.strip()[:120]}")
        # check raw chat id hardcoded as literal assignment (not via config)
        # we already covered, but also check for direct numeric assignment like chat_id = 7830528991 in bot.py
        if f.name == "bot.py":
            # allow config.allowed_chat_id references, but not literal 783...
            for i, line in enumerate(txt.splitlines(), 1):
                if "7830528991" in line and "config" not in line and "ALLOWED_CHAT_ID" not in line:
                    # if it's in comment or log, maybe ignore? but flag
                    if "7830528991" in line:
                        hits.append(f"{f.relative_to(REPO)}:{i} hardcoded chat id 7830528991: {line.strip()[:120]}")
    assert hits == [], "Hardcoded credentials found:\n" + "\n".join(hits)


def test_no_hardcoded_handles_in_messages():
    # Check via imported module — robust vs regex fragile with parens inside strings
    import ui.messages as msgs_mod

    for block_name in ["TEMPLATES_TEXT", "DOCS_TEXT", "HELP_TEXT", "CONTROL_CENTER_TEXT"]:
        block = getattr(msgs_mod, block_name, "")
        assert "@mventor" not in block, f"{block_name} should not hardcode @mventor"
        assert "@videosforall" not in block.lower(), f"{block_name} should not hardcode handle"
    # Also check scripts — exclude check_no_hardcoded.py which intentionally lists handles to detect
    for f in (REPO / "scripts").glob("*.py"):
        if f.resolve() == (REPO / "scripts" / "check_no_hardcoded.py").resolve():
            continue
        t = f.read_text(encoding="utf-8", errors="ignore")
        # scripts may reference handles via config, but not hardcode literal handle in default values
        # Check that default handle params are "" or None, not "@mventor"
        if "@mventor" in t:
            # allow if in comment explaining old behavior? but we flag
            for i, line in enumerate(t.splitlines(), 1):
                if "@mventor" in line and not line.strip().startswith("#"):
                    # check if line is inside docstring? still flag
                    assert False, f"scripts/{f.name}:{i} hardcodes @mventor: {line.strip()[:120]}"
