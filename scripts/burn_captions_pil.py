"""Burn captions INTO video pixels (Pillow draws text, ffmpeg encodes).

No soft-sub file. The text is rendered onto each frame and encoded — it is
physically part of the video. Pillow handles Arabic/RTL and any TTF font.

Caption text is read from a plain editable text file (jobs/media/caption_text.txt),
one line per caption card. Edit it, rerun, done.

Usage:
  python scripts/burn_captions_pil.py [--video <in>] [--text <file>] [--out <path>] [--font <ttf>]
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import config

FFMPEG = config.ffmpeg_dir / "ffmpeg.exe"
# Strong Arabic + Latin support (or swap for arialbd.ttf for Latin only)
DEFAULT_FONT = Path(r"C:\Windows\Fonts\DUBAI-BOLD.TTF")


def load_frames(video: Path, out_dir: Path) -> list[Path]:
    """Decode a video to PNG frames with ffmpeg (raw, no audio)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(FFMPEG), "-y", "-v", "error",
        "-i", str(video),
        "-an",
        str(out_dir / "f_%04d.png"),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg decode failed:\n{proc.stderr[-1200:]}")
    return sorted(out_dir.glob("f_*.png"))


def draw_caption(img: Image.Image, text: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    """Draw text centered with a black outline, big and readable."""
    draw = ImageDraw.Draw(img)
    w, h = img.size
    # word-wrap the text to fit 90% of width
    words = text.split()
    lines, cur = [], ""
    for wd in words:
        probe = (cur + " " + wd).strip()
        if draw.textlength(probe, font=font) <= w * 0.9:
            cur = probe
        else:
            lines.append(cur)
            cur = wd
    lines.append(cur)

    line_h = font.size + 14
    total_h = line_h * len(lines)
    y = int(h - total_h - h * 0.06)  # near bottom, 6% margin
    for ln in lines:
        tw = draw.textlength(ln, font=font)
        x = int((w - tw) / 2)
        # outline stroke for readability on any background
        draw.text((x, y), ln, font=font, fill="white", stroke_width=3, stroke_fill="black")
        y += line_h
    return img


def probe_fps(video: Path) -> float:
    """Read the video's real frame rate via ffprobe (stream avg_frame_rate)."""
    cmd = [
        str(config.ffmpeg_dir / "ffprobe.exe"), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate,r_frame_rate",
        "-of", "default=noprint_wrappers=1",
        str(video),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    for line in (proc.stdout or "").splitlines():
        if line.startswith("avg_frame_rate=") or line.startswith("r_frame_rate="):
            rate = line.split("=", 1)[1].strip()
            if "/" in rate:
                num, den = rate.split("/")
                try:
                    if float(den) != 0:
                        return round(float(num) / float(den), 3)
                except ValueError:
                    pass
    return 30.0


def burn(video: Path, text_file: Path, out: Path, font_path: Path) -> Path:
    lines = [ln.strip() for ln in text_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        raise SystemExit(f"no caption lines in {text_file}")

    frames = load_frames(video, out.parent / "_frames")
    n = len(frames)
    fps = probe_fps(video)
    font_size = max(24, int(0.11 * 720))  # big relative to a 720-high frame
    font = ImageFont.truetype(str(font_path), font_size)

    for i, fp in enumerate(frames):
        img = Image.open(fp).convert("RGB")
        # time-slice the caption lines evenly across the clip
        idx = min(int(i / max(n, 1) * len(lines)), len(lines) - 1)
        img = draw_caption(img, lines[idx], font)
        img.save(fp)
    print(f"captioned {n} frames at {fps}fps")

    cmd = [
        str(FFMPEG), "-y", "-v", "error",
        "-framerate", str(fps),
        "-i", str(out.parent / "_frames" / "f_%04d.png"),
        "-c:v", "libx264", "-crf", "23", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg encode failed:\n{proc.stderr[-1200:]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", default=str(config.jobs_dir / "media" / "montage_test.mp4"))
    ap.add_argument("--text", default=str(config.jobs_dir / "media" / "caption_text.txt"))
    ap.add_argument("--out", default=str(config.jobs_dir / "media" / "montage_captioned.mp4"))
    ap.add_argument("--font", default=str(DEFAULT_FONT))
    args = ap.parse_args()
    out = burn(Path(args.video), Path(args.text), Path(args.out), Path(args.font))
    print(f"OK -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
