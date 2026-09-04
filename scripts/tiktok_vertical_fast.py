"""Fast vertical TikTok: ffmpeg does the heavy lifting, Pillow renders ONE overlay PNG.

No per-frame Python loop. The caption card + TikTok watermark are drawn ONCE
to a transparent 1080x1920 PNG, then ffmpeg composites everything in a single
filter_complex pass. 51s video: ~20-30s instead of 3 minutes.

Usage (run in YOUR terminal window, not the agent CLI):
  python scripts/tiktok_vertical_fast.py --source jobs/media/qaid_seg.mp4 --out jobs/media/qaid_tiktok.mp4 --title "سعدني في الحضارة" --subtitle "صفات القائد" --style card

Burns the caption IN the pixels (Pillow drawText with arabic shaping) and the
TikTok note logo + @mventor handle, all physically in the video.

Templates:
  01 = 9:16 vertical + Majalla card (0.94 wide, 1.95x tall) + @mventor watermark
  00 = same 9:16 vertical BUT no card burned (--title "" --subtitle "") — clean video, optional watermark via --handle / --no-watermark
     TikTok post description (text under video) is NOT burned into pixels.
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from config import config
from scripts.caption_card import render, tiktok_watermark

FFMPEG = config.ffmpeg_dir / "ffmpeg.exe"
FFPROBE = config.ffmpeg_dir / "ffprobe.exe"
W, H = 1080, 1920


def probe_duration(path: Path) -> float:
    cmd = [str(FFPROBE), "-v", "error", "-show_entries", "format=duration",
           "-of", "default=nw=1:nk=1", str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def make_overlay(title: str, subtitle: str, style: str, accent: str, handle: str) -> Path:
    """Render ONE transparent overlay PNG with caption card + watermark.

    Template 00: title == "" and subtitle == "" => no card is drawn, only watermark if handle != "".
    Result is fully transparent (or watermark-only) and ffmpeg still does 9:16 conversion correctly.
    """
    def hex_rgba(h: str):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0,2,4)) + (255,)
    accent_rgba = hex_rgba(accent)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # ponytail: no overlay file vs transparent png — transparent still compositable, simplest path
    if title or subtitle:
        img = render(img, title, subtitle, style=style, accent=accent_rgba)
    if handle:
        img = tiktok_watermark(img, handle=handle, size_frac=0.055, pad_frac=0.035, corner="top-left")
    tmp = Path(tempfile.gettempdir()) / f"tg_overlay_{abs(hash((title,subtitle,style,handle)))%100000}.png"
    img.save(tmp)
    return tmp


def vertical_fast(source: Path, out: Path, title: str, subtitle: str, style: str, accent: str, handle: str):
    overlay = make_overlay(title, subtitle, style, accent, handle)
    dur = probe_duration(source)
    if dur <= 0:
        dur = 60  # fallback
    # ffmpeg: blurred bg + sharp centered fg + overlay PNG
    # -loop 1 for image, -t to limit overlay stream to video duration
    filter_c = (
        "[0:v]split=2[bg][fg];"
        f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=18[bgblur];"
        f"[fg]scale={W}:-1[fg1];"
        "[bgblur][fg1]overlay=(W-w)/2:(H-h)/2:shortest=1[vert];"
        "[vert][1:v]overlay=0:0:shortest=1,format=yuv420p[out]"
    )
    cmd = [
        str(FFMPEG), "-y", "-v", "error",
        "-i", str(source),
        "-loop", "1", "-t", f"{dur:.3f}", "-i", str(overlay),
        "-filter_complex", filter_c,
        "-map", "[out]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-movflags", "+faststart",
        str(out),
    ]
    print(" ".join(cmd[:6]) + " ... (ffmpeg fast pass)")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg fast vertical failed:\n{proc.stderr[-1500:]}")
    print(f"OK -> {out}  ({W}x{H}, {dur:.1f}s)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="سعدني في الحضارة")
    ap.add_argument("--subtitle", default="صفات القائد")
    ap.add_argument("--style", default="card", choices=["card", "pill", "banner"])
    ap.add_argument("--accent", default="#EAB308")
    ap.add_argument("--handle", default="@mventor")
    ap.add_argument("--no-watermark", action="store_true")
    args = ap.parse_args()
    handle = "" if args.no_watermark else args.handle
    vertical_fast(Path(args.source), Path(args.out), args.title, args.subtitle, args.style, args.accent, handle)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
