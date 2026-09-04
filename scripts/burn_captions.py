"""Burn configurable big-font captions into a video (ffmpeg drawtext).

Caption text is read from a plain text file — edit it, rerun, done.
Each line = one caption card. Default file: jobs/media/caption_text.txt
(contains MVENTOR-TEST / TEST-CAPTIONS — fully editable.)

Usage:
  python scripts/burn_captions.py [--video <input>] [--text <file>] [--out <path>]
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from config import config

FFMPEG = config.ffmpeg_dir / "ffmpeg.exe"
FONT_BOLD = r"C:\Windows\Fonts\arialbd.ttf".replace("\\", "/")
FONT_REG = r"C:\Windows\Fonts\arial.ttf".replace("\\", "/")


def build_filter(lines: list[str]) -> str:
    """One drawtext card per line, centered, big font, timed across the clip.

    The drive-letter colon in the font path is escaped (`C\\:/`) so ffmpeg's
    filter parser does not treat it as an option separator.
    """
    filters = []
    n = len(lines)
    for i, text in enumerate(lines):
        text = text.replace("'", r"\'").replace(":", r"\:").replace(",", r"\,")
        start = i * (10.0 / n)
        dur = 10.0 / n
        size = "h*0.14"  # 14% of frame height -> big
        font = FONT_BOLD.replace(":", r"\:")
        filters.append(
            f"drawtext=fontfile='{font}':text='{text}':"
            f"fontcolor=white:fontsize={size}:line_spacing=12:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:"
            f"enable='between(t,{start:.2f},{start + dur - 0.2:.2f})':"
            f"borderw=3:bordercolor=black"
        )
    return ",".join(filters)


def burn(video: Path, text_file: Path, out: Path) -> None:
    lines = [ln.strip() for ln in text_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        raise SystemExit(f"no caption lines in {text_file}")
    vf = build_filter(lines)
    cmd = [
        str(FFMPEG), "-y", "-v", "error",
        "-i", str(video),
        "-vf", vf,
        "-map", "0:v", "-map", "0:a?",
        "-c:v", "libx264", "-crf", "23", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        str(out),
    ]
    print(" ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg failed:\n{proc.stderr[-1500:]}")
    print(f"OK -> {out}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", default=str(config.jobs_dir / "media" / "input.mp4"))
    ap.add_argument("--text", default=str(config.jobs_dir / "media" / "caption_text.txt"))
    ap.add_argument("--out", default=str(config.jobs_dir / "media" / "out_captioned.mp4"))
    args = ap.parse_args()
    burn(Path(args.video), Path(args.text), Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
