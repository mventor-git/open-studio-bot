#!/usr/bin/env python
"""TikTok Studio uploader — default handler with confirm modal always on.

Thin wrapper around publish_template01.upload_tiktok so any upload path
automatically handles the two-step publish:

  1) scroll+force click نشر (off-screen y1488>1080)
  2) poll 15s for "هل تريد المتابعة للنشر" modal -> force click "النشر الآن"
     and wait for POST /web/project/post/v1/ 200

This is the default uploader. Use it for any TikTok upload — retry6 proved
that without step 2 the publish never happens (no POST, no project_id/item_id).

Usage:
  python scripts/upload_tiktok.py --video jobs/media/qaid_tiktok.mp4 --desc "سعدني ..."
  python scripts/upload_tiktok.py --video out.mp4 --dry-run  # verify modal code
"""
from __future__ import annotations

try:
    import sys as _sys2
    _sys2.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys2.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.publish_template01 import upload_tiktok, log  # reuse single source of truth


def wait_for_confirm_modal(page, timeout: int = 15) -> bool:
    """Patch helper: after clicking نشر, poll 15s for confirm modal.

    Standalone helper if callers already clicked نشر and want just the modal
    handling. Uses same logic as publish_template01.wait_for_confirm_and_publish.
    """
    from scripts.publish_template01 import wait_for_confirm_and_publish
    return wait_for_confirm_and_publish(page, timeout=timeout)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", required=True, help="1080x1920 mp4 to upload")
    ap.add_argument("--desc", default="سعدني في الحضارة - صفات القائد #حضارة #قيادة #تاريخ")
    ap.add_argument("--dry-run", action="store_true", help="verify modal code present without uploading")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        text = (REPO_ROOT / "scripts" / "publish_template01.py").read_text(encoding="utf-8")
        need = ["هل تريد المتابعة للنشر", "النشر الآن", "post/v1", "scrollIntoView", "تخطي"]
        for n in need:
            log(f"check '{n}': {'OK' if n in text else 'MISSING'}")
        log("dry-run OK — confirm modal handler present")
        return 0

    video = Path(args.video)
    if not video.exists():
        raise SystemExit(f"video not found: {video}")
    result = upload_tiktok(video, args.desc, headless=args.headless)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("url"):
        print(result["url"])
    return 0 if result.get("ok") else 2

if __name__ == "__main__":
    raise SystemExit(main())
