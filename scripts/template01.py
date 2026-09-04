"""Template 01 — single command: captions + animated cuts.

Takes a source video and a caption text file, cuts the source into one
segment per caption line, burns each caption into the segment pixels (Pillow),
then joins all segments with animated crossfade transitions (ffmpeg xfade).

Usage:
  python scripts/template01.py \
      --source <in.mp4> --text <caption_text.txt> --out <out.mp4>
      [--cuts N] [--transition fade|slideleft|wiperight] [--dur <per-cut-s>]
      [--font <ttf>] [--gap <s>]

Example:
  python scripts/template01.py --source jobs/media/input.mp4 \
      --text jobs/media/caption_text.txt --out jobs/media/template01.mp4
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import config

FFMPEG = config.ffmpeg_dir / "ffmpeg.exe"
FFPROBE = config.ffmpeg_dir / "ffprobe.exe"
DEFAULT_FONT = Path(r"C:\Windows\Fonts\DUBAI-BOLD.TTF")


def probe(video: Path, entry: str) -> float | int | str:
    """Return a single fmt/stream field from ffprobe."""
    cmd = [str(FFPROBE), "-v", "error", "-show_entries", entry,
           "-of", "default=noprint_wrappers=1:nokey=1", str(video)]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    lines = [l for l in out.splitlines() if l.strip()]
    return lines[0] if lines else ""


def run(cmd: list[str], what: str) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"{what} failed:\n{p.stderr[-1500:]}")


def cut_segment(src: Path, out: Path, start: float, dur: float) -> None:
    """Extract one segment; add a 0.4s fade-in/out so cuts feel animated."""
    cmd = [
        str(FFMPEG), "-y", "-v", "error",
        "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
        "-vf", "fade=t=in:st=0:d=0.4,fade=t=out:st=%.3f:d=0.4" % max(dur - 0.4, 0.4),
        "-c:v", "libx264", "-crf", "23", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-an",
        str(out),
    ]
    run(cmd, f"cut segment {out.name}")


def draw_caption(img: Image.Image, text: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    draw = ImageDraw.Draw(img)
    w, h = img.size
    words = text.split()
    lines, cur = [], ""
    for wd in words:
        probe_t = (cur + " " + wd).strip()
        if draw.textlength(probe_t, font=font) <= w * 0.9:
            cur = probe_t
        else:
            lines.append(cur); cur = wd
    lines.append(cur)
    line_h = font.size + 14
    y = int(h - line_h * len(lines) - h * 0.06)
    for ln in lines:
        tw = draw.textlength(ln, font=font)
        draw.text((int((w - tw) / 2), y), ln, font=font, fill="white",
                  stroke_width=3, stroke_fill="black")
        y += line_h
    return img


def caption_video(seg: Path, text: str, font_path: Path) -> None:
    """Burn a caption into a segment (decode -> draw -> re-encode)."""
    work = seg.parent / f"_cap_{seg.stem}"
    work.mkdir(exist_ok=True)
    run([str(FFMPEG), "-y", "-v", "error", "-i", str(seg), "-an",
         str(work / "f_%04d.png")], "decode segment")
    frames = sorted(work.glob("f_*.png"))
    fps = float(probe(seg, "stream=avg_frame_rate").split("/")[0]) if "/" in probe(seg, "stream=avg_frame_rate") else 15.0
    font = ImageFont.truetype(str(font_path), max(24, int(0.11 * 720)))
    for fp in frames:
        draw_caption(Image.open(fp).convert("RGB"), text, font).save(fp)
    run([str(FFMPEG), "-y", "-v", "error",
         "-framerate", str(fps), "-i", str(work / "f_%04d.png"),
         "-c:v", "libx264", "-crf", "23", "-preset", "fast", "-pix_fmt", "yuv420p",
         "-an", str(seg)], "encode captioned segment")


def concat_xfade(segs: list[Path], out: Path, transition: str, gap: float) -> None:
    """Join segments with animated crossfades into one file."""
    n = len(segs)
    inputs: list[str] = []
    for s in segs:
        inputs += ["-i", str(s)]
    # build filter_complex: each xfade needs cumulative offset minus gap
    filters: list[str] = []
    prev_label = "0:v"
    offset = 0.0
    durations = [float(probe(s, "format=duration")) for s in segs]
    for i in range(1, n):
        offset += durations[i - 1] - gap
        label = f"x{i}"
        filters.append(
            f"[{prev_label}][{i}:v]xfade=transition={transition}:"
            f"duration={gap}:offset={offset:.3f}[{label}]"
        )
        prev_label = label
    graph = ";".join(filters)
    cmd = [str(FFMPEG), "-y", "-v", "error", *inputs,
           "-filter_complex", graph, "-map", f"[{prev_label}]",
           "-c:v", "libx264", "-crf", "23", "-preset", "fast", "-pix_fmt", "yuv420p",
           "-an", str(out)]
    # single xfade needs no map label if n==2 handled by loop; label always present
    run(cmd, "crossfade concat")


def template01(source: Path, text: Path, out: Path, font_path: Path,
               cuts: int, transition: str, dur: float, gap: float) -> None:
    lines = [ln.strip() for ln in text.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        raise SystemExit(f"no caption lines in {text}")
    total = float(probe(source, "format=duration"))
    per = dur if dur > 0 else total / cuts
    src_fps = float(probe(source, "stream=avg_frame_rate").split("/")[0]) if "/" in probe(source, "stream=avg_frame_rate") else 15.0

    workdir = out.parent / "_t01"
    workdir.mkdir(exist_ok=True)
    segs: list[Path] = []
    for i in range(min(cuts, len(lines))):
        start = i * per
        seg = workdir / f"seg_{i:02d}.mp4"
        cut_segment(source, seg, start, per)
        caption_video(seg, lines[i % len(lines)], font_path)
        segs.append(seg)
    concat_xfade(segs, out, transition, gap)
    print(f"OK -> {out}  ({len(segs)} cuts, '{transition}' transitions, {per:.1f}s each)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--font", default=str(DEFAULT_FONT))
    ap.add_argument("--cuts", type=int, default=4, help="how many segments/captions to make")
    ap.add_argument("--transition", default="fade",
                    choices=["fade", "slideleft", "slideright", "wiperight", "circleopen", "dissolve"])
    ap.add_argument("--dur", type=float, default=0, help="seconds per cut (0 = divide source evenly)")
    ap.add_argument("--gap", type=float, default=0.5, help="crossfade duration (s)")
    args = ap.parse_args()
    template01(Path(args.source), Path(args.text), Path(args.out), Path(args.font),
               args.cuts, args.transition, args.dur, args.gap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
