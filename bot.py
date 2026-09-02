"""tg-montage bot entry point.

Run modes:
  python bot.py                 # long polling (requires BOT_TOKEN)
  python bot.py --check-config  # validate config and exit (T1 acceptance)
"""
from __future__ import annotations

import sys

from config import check_config, config


def check_config_mode() -> int:
    problems = check_config()
    if problems:
        print("CONFIG PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("config OK")
    print(f"  jobs dir:     {config.jobs_dir}")
    print(f"  waterfox:     {config.waterfox_profile}")
    print(f"  opencode:     {config.opencode_server_url}")
    print(f"  bot token:    set ({len(config.bot_token)} chars)")
    return 0


def main() -> int:
    if "--check-config" in sys.argv:
        return check_config_mode()

    problems = check_config()
    if problems:
        for p in problems:
            print(f"CONFIG: {p}")
        print("Fix .env before starting the bot.")
        return 1

    # T6 wires the real handlers; until then the bot validates and exits.
    print("bot handlers are implemented in a later ticket (T6). Exiting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
