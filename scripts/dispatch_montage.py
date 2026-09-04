import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents.opencode_client import run_job

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "jobs" / "media" / "input.mp4"
OUT = REPO / "jobs" / "media" / "out_tiktok.mp4"
OM_REPO = Path.home() / "OpenStudioBot"  # ponytail: sibling checkout, override here if elsewhere
FFMPEG = REPO / "tools" / "ffmpeg-9.0.1-essentials_build" / "bin"

prompt = f"""You are the Open Studio Bot production agent working in {OM_REPO}.
TASK: Cut a 10-second montage from {SRC} (a ~19s clip) -> {OUT}.
Use the bundled ffmpeg at {FFMPEG} (ffmpeg.exe / ffprobe.exe there).
Steps:
1. ffprobe the source.
2. ffmpeg -ss 0 -t 10 -i <src> -vf "fade=t=in:st=0:d=1,fade=t=out:st=9:d=1" -c:v libx264 -pix_fmt yuv420p -an {OUT}
3. ffprobe the output to confirm it exists and is 10s.
Reply with ONLY one line: {{"ok":true,"output":"{OUT}","error":""}} or {{"ok":false,"output":"","error":"..."}}"""

result = run_job(prompt, agent="build", model="Claude-Free", location_dir=OM_REPO, hard_timeout=600)
print("finish:", result["finish"])
print("error:", result["error"])
print("text_tail:", result["text"][-700:])
