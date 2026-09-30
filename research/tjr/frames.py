"""
frames.py: turns a trading video into the chart pictures worth studying.

    python research/tjr/frames.py path/to/video.mp4 [more videos...]

For each video it writes research/tjr/raw/<name>/ (not committed: it's the video owner's content):
  shots/   one picture each time the CHART changes (webcam corner and ticker bar ignored),
           named by time in the video, e.g. 0012_03m20s.jpg
  sheets/  the same pictures four to a page (2x2), for skimming a whole lesson quickly
Only keyframes are decoded, so a 20-minute video takes seconds.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw

RAW = Path(__file__).resolve().parent / "raw"
CHANGE = 6.0          # average brightness change (0-255) in the chart area that counts as "new picture"
MIN_GAP = 3.0         # seconds: ignore changes closer together than this (drawing in progress)


def slug(path: Path) -> str:
    return re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")[:60] or "video"


def keyframes(video: Path, folder: Path) -> list:
    """Every keyframe as (seconds, file)."""
    folder.mkdir(parents=True, exist_ok=True)
    run = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "info", "-skip_frame", "nokey", "-i", str(video),
                          "-vf", "scale=1280:-2,showinfo", "-fps_mode", "vfr", "-q:v", "3", str(folder / "%05d.jpg")],
                         capture_output=True, text=True)
    times = [float(t) for t in re.findall(r"pts_time:([0-9.]+)", run.stderr)]
    files = sorted(folder.glob("*.jpg"))
    return list(zip(times, files))


def chart_area(image: Image.Image) -> np.ndarray:
    """A small grey copy of the picture without the webcam (bottom right) and the top bars."""
    small = np.asarray(image.convert("L").resize((160, 90)), dtype=float)
    small = small[8:, :]                        # top ~9%: browser tabs, live ticker prices
    small[52:, 106:] = 0                        # bottom-right third: the webcam
    return small


def stamp(seconds: float) -> str:
    return f"{int(seconds // 60):02d}m{int(seconds % 60):02d}s"


def pick(frames: list, out: Path) -> list:
    out.mkdir(parents=True, exist_ok=True)
    kept, last, last_t = [], None, -MIN_GAP
    for t, f in frames:
        image = Image.open(f)
        area = chart_area(image)
        if last is None or (np.abs(area - last).mean() > CHANGE and t - last_t >= MIN_GAP):
            name = out / f"{len(kept) + 1:04d}_{stamp(t)}.jpg"
            image.save(name, quality=88)
            kept.append((t, name))
            last, last_t = area, t
    return kept


def sheets(kept: list, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    for i in range(0, len(kept), 4):
        page = Image.new("RGB", (1280, 720), "white")
        for j, (t, f) in enumerate(kept[i:i + 4]):
            tile = Image.open(f).resize((636, 356))
            x, y = (j % 2) * 644, (j // 2) * 364
            page.paste(tile, (x, y))
            ImageDraw.Draw(page).rectangle([x, y, x + 86, y + 18], fill="black")
            ImageDraw.Draw(page).text((x + 4, y + 3), f"#{i + j + 1} {stamp(t)}", fill="white")
        page.save(out / f"sheet_{i // 4 + 1:03d}.jpg", quality=85)


def study(video: Path) -> Path:
    folder = RAW / slug(video)
    with tempfile.TemporaryDirectory() as tmp:
        kept = pick(keyframes(video, Path(tmp)), folder / "shots")
    sheets(kept, folder / "sheets")
    print(f"  {video.name}: {len(kept)} chart pictures, {(len(kept) + 3) // 4} sheets -> {folder}")
    return folder


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for name in sys.argv[1:]:
        study(Path(name))
