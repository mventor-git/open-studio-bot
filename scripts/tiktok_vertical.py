"""Convert a 16:9 video to 9:16 vertical TikTok with a styled Arabic caption card.

Blurred 16:9 background fills the top/bottom; the sharp video is centered in a
9:16 window; a custom CSS-style caption card is drawn at the bottom (Pillow).

Usage:
  python scripts/tiktok_vertical.py --source <in.mp4> --out <out.mp4>
      [--title "Example Title"] [--subtitle "Example Subtitle"]
      [--style card|pill|banner] [--accent "#EAB308"]
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from config import config
from scripts.caption_card import render, shape_ar, tiktok_watermark

FFMPEG = config.ffmpeg_dir / "ffmpeg.exe"
CAPTION = r"C:\Users\Mventor\tg-montage\jobs\media\caption_card.ttf"  # unused fallback


def hex_to_rgb(hexstr: str) -> tuple:
    h = hexstr.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


def verticalize(source: Path, out: Path, title: str, subtitle: str,
                style: str, accent_hex: str, width: int = 1080, height: int = 1920,
                handle: str | None = None, watermark: bool = True) -> Path:
    if handle is None:
        try:
            from config import config as _cfg
            handle = _cfg.watermark_handle or ""
        except Exception:
            handle = ""
    cap = cv2.VideoCapture(str(source))
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    # write temp video-only first, then mux original audio back (so captions don't drop sound)
    tmp_vid = out.with_suffix(".nov0.mp4")
    writer = cv2.VideoWriter(str(tmp_vid), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    accent = hex_to_rgb(accent_hex)

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.resize(frame, (src_w, src_h))
        # 1) blurred full-frame background scaled to fill 9:16
        bg = cv2.resize(frame, (width, height))
        bg = cv2.GaussianBlur(bg, (0, 0), sigmaX=18)
        # 2) sharp 16:9 letterboxed to center window (fit width, centered vertically)
        scale = width / src_w
        new_h = int(src_h * scale)
        if new_h <= height:
            sharp = cv2.resize(frame, (width, new_h))
            y_off = (height - new_h) // 2
            bg[y_off:y_off + new_h, :] = sharp
        # 3) draw caption card + TikTok watermark on the composed frame
        pil = Image.fromarray(cv2.cvtColor(bg, cv2.COLOR_BGR2RGB))
        pil = render(pil, title, subtitle, style=style, accent=accent)
        if watermark and handle:
            pil = tiktok_watermark(pil, handle=handle, size_frac=0.055, pad_frac=0.035, corner="top-left")
        bg = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        writer.write(bg)

    cap.release()
    writer.release()

    # 4) mux original audio back (ffmpeg re-encodes video to h264 for TikTok compatibility + audio)
    #    Use config ffmpeg bin for mux
    tmp_mux = out.with_suffix(".tmp.mp4")
    cmd = [
        str(FFMPEG), "-y", "-v", "error",
        "-i", str(tmp_vid),
        "-i", str(source),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        str(tmp_mux),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode == 0:
        tmp_vid.unlink(missing_ok=True)
        tmp_mux.replace(out)
    else:
        # no audio fallback: just transcode the video
        print(f"audio mux warning: {p.stderr[:600]}")
        tmp_vid.replace(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--style", default="card", choices=["card", "pill", "banner"])
    ap.add_argument("--accent", default="#EAB308")
    ap.add_argument("--handle", default=None, help="watermark handle, defaults to WATERMARK_HANDLE env (empty=skip)")
    ap.add_argument("--no-watermark", action="store_true")
    args = ap.parse_args()
    if args.handle is None:
        try:
            from config import config as _cfg
            args.handle = _cfg.watermark_handle or ""
        except Exception:
            args.handle = ""
    verticalize(Path(args.source), Path(args.out), args.title, args.subtitle,
                args.style, args.accent, handle=args.handle, watermark=not args.no_watermark)
    print(f"OK -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
