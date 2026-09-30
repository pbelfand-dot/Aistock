"""
recaps.py: turns the Trade Recap videos (a GitHub release, 42 GB) into study folders, a few at a time.

    python research/tjr/recaps.py inventory            # list the release's videos -> recaps/inventory.csv
    python research/tjr/recaps.py prepare 1 2 3 4 5    # these inventory numbers: download, pictures, transcript
    python research/tjr/recaps.py table                # rebuild recaps/trades.csv from recaps/records/*.json

Each video gets raw/recaps/<NNN>/ (not committed: it's the video owner's content):
  info.json        name, size, duration, resolution, what the title claims
  shots/           the chart at full size, once per "scene": the LAST picture before the chart changes,
                   so drawings (position boxes, levels) are complete. Named 0007_03m20s-03m45s.jpg
  sheets/          the same pictures four to a page, for a quick overview (too small to read prices)
  transcript.txt   what's said, [mm:ss] per 15 s: offline speech-to-text, rough
The video itself is deleted once done. Our analysis (recaps/records/, recaps/trades.csv) is committed.

The uploads were saved with a web-form wrapper around each file (a "------boundary / Content-Disposition"
header and a closing boundary); unwrap() strips it and the MP4 inside is intact.
"""
import csv
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

import frames

HERE = Path(__file__).resolve().parent
OUT = HERE / "recaps"
RAW = HERE / "raw" / "recaps"
RELEASE = "https://api.github.com/repos/pbelfand-dot/Aistock/releases/399622522"
ASSET = "https://api.github.com/repos/pbelfand-dot/Aistock/releases/assets/"
MAX_SHOTS = 48                    # pictures per video at most (long live sessions get a coarser cut)


# ------------------------------------------------------------------ inventory
def curl_json(url):
    return json.loads(subprocess.run(["curl", "-sSf", url], capture_output=True, check=True).stdout)


def title_claim(name):
    m = re.search(r"(Making|Losing)\.([\d.]+)", name)
    if not m:
        m2 = re.search(r"Made\.([\d.]+)|Lost\.([\d.]+)|Into\.([\d.]+)", name)
        return f"title says {m2.group(0).replace('.', ' ', 1)}" if m2 else ""
    return f"title says {m.group(1).lower()} ${m.group(2).replace('.', ',')}"


def kind(name):
    n = name.lower()
    if n.startswith("pov_"):
        return "lifestyle"
    if "live.day.trading" in n:
        return "live session"
    if re.match(r"\d", n) or "weekly" in n:
        return "dated recap/analysis"
    return "breakdown"


def inventory():
    assets, page = [], 1
    while True:
        got = curl_json(f"{RELEASE}/assets?per_page=100&page={page}")
        assets += got
        if len(got) < 100:
            break
        page += 1
    assets.sort(key=lambda a: a["id"])                       # upload order (the folder's order)
    OUT.mkdir(exist_ok=True)
    with open(OUT / "inventory.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n", "asset_id", "file", "size_mb", "kind", "title_claim"])
        for i, a in enumerate(assets, 1):
            w.writerow([i, a["id"], a["name"], round(a["size"] / 1e6), kind(a["name"]), title_claim(a["name"])])
    print(f"{len(assets)} videos, {sum(a['size'] for a in assets) / 1e9:.1f} GB -> {OUT / 'inventory.csv'}")


def rows():
    with open(OUT / "inventory.csv") as f:
        return {int(r["n"]): r for r in csv.DictReader(f)}


# ------------------------------------------------------------------ one video
def unwrap(src: Path, dst: Path):
    with open(src, "rb") as f:
        head = f.read(4096)
        if head[4:8] == b"ftyp":                              # already a plain MP4
            src.rename(dst)
            return
        start = head.index(b"\r\n\r\n") + 4
        boundary = head[:head.index(b"\r\n")]
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - len(boundary) - 64))
        tail = f.read()
        end = size - len(tail) + tail.rindex(b"\r\n" + boundary)
        f.seek(start)
        left = end - start
        with open(dst, "wb") as o:
            while left > 0:
                chunk = f.read(min(1 << 24, left))
                o.write(chunk)
                left -= len(chunk)
    src.unlink()


def probe(video: Path):
    err = subprocess.run([frames.imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(video)],
                         capture_output=True, text=True).stderr
    d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    res = re.search(r"Video: h264.*?, (\d+)x(\d+)", err)
    return (int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))) if d else None, \
        f"{res.group(1)}x{res.group(2)}" if res else None


def scenes(keys, change):
    """Group keyframes into scenes (the chart area barely changes inside one). Returns [(t0, t1, last_file)]."""
    out, ref = [], None
    for t, f in keys:
        area = frames.chart_area(Image.open(f))
        if ref is None or np.abs(area - ref).mean() > change:
            out.append([t, t, f])
            ref = area
        else:
            out[-1][1], out[-1][2] = t, f
    return out


def shots(video: Path, folder: Path, tmp: Path):
    keys = frames.keyframes(video, tmp)
    change = frames.CHANGE
    picked = scenes(keys, change)
    while len(picked) > MAX_SHOTS:
        change *= 1.3
        picked = scenes(keys, change)
    (folder / "shots").mkdir(parents=True, exist_ok=True)
    kept = []
    for i, (t0, t1, f) in enumerate(picked, 1):
        name = folder / "shots" / f"{i:04d}_{frames.stamp(t0)}-{frames.stamp(t1)}.jpg"
        Image.open(f).save(name, quality=90)
        kept.append((t0, name))
    frames.sheets(kept, folder / "sheets")
    return len(kept)


def transcript(video: Path, folder: Path):
    import ingest_video
    pcm = ingest_video.audio_pcm(video)
    step = ingest_video.CHUNK * ingest_video.RATE * 2
    from pocketsphinx import Decoder
    decoder = Decoder(samprate=ingest_video.RATE)
    lines = []
    for start in range(0, len(pcm), step):
        piece = pcm[start:start + step]
        samples = np.frombuffer(piece, dtype=np.int16).astype(float)
        if samples.size == 0 or np.sqrt((samples ** 2).mean()) < 100:     # silence: skip
            continue
        decoder.start_utt()
        decoder.process_raw(piece, full_utt=True)
        decoder.end_utt()
        text = decoder.hyp().hypstr.strip() if decoder.hyp() else ""
        if text:
            lines.append(f"{ingest_video.stamp(start / (ingest_video.RATE * 2))} {text}")
    (folder / "transcript.txt").write_text(
        f"# {video.name}\n# offline speech-to-text (pocketsphinx): ROUGH, many words wrong; use as hints only\n"
        + "\n".join(lines) + "\n")
    return len(lines)


def prepare_one(row):
    n = int(row["n"])
    folder = RAW / f"{n:03d}"
    if (folder / "info.json").exists() and json.loads((folder / "info.json").read_text()).get("status") == "ok":
        return n, "already done"
    folder.mkdir(parents=True, exist_ok=True)
    work = RAW / "_work" / f"{n:03d}"
    work.mkdir(parents=True, exist_ok=True)
    info = {"n": n, "asset_id": row["asset_id"], "file": row["file"], "size_mb": int(row["size_mb"]),
            "kind": row["kind"], "title_claim": row["title_claim"]}
    t = time.time()
    try:
        wrapped, video = work / "download.bin", work / "video.mp4"
        subprocess.run(["curl", "-sSfL", "--retry", "4", "-H", "Accept: application/octet-stream",
                        "-o", str(wrapped), ASSET + row["asset_id"]], check=True)
        unwrap(wrapped, video)
        info["duration_s"], info["resolution"] = probe(video)
        if not info["duration_s"]:
            raise RuntimeError("the file does not open as a video")
        info["shots"] = shots(video, folder, work / "keys")
        info["transcript_lines"] = transcript(video, folder)
        info["status"] = "ok"
    except Exception as e:                                                   # say so; never pretend
        info["status"] = f"failed: {type(e).__name__}: {e}"
    finally:
        subprocess.run(["rm", "-rf", str(work)])
    info["seconds_to_prepare"] = round(time.time() - t)
    (folder / "info.json").write_text(json.dumps(info, indent=1))
    return n, info["status"]


def prepare(numbers, workers=4):
    inv = rows()
    with ProcessPoolExecutor(workers) as pool:
        for n, status in pool.map(prepare_one, [inv[k] for k in numbers]):
            print(f"{n:03d}: {status}", flush=True)


# ------------------------------------------------------------------ the cumulative table
COLUMNS = ["n", "trade", "date", "instrument", "direction", "timeframes", "setup", "entry", "stop", "target",
           "exit", "size", "result", "r_multiple", "r_basis", "claimed_pnl", "pnl_verified", "mistakes", "evidence"]


def cell(field):
    if not isinstance(field, dict):
        return "" if field is None else str(field)
    v = field.get("value")
    v = "; ".join(map(str, v)) if isinstance(v, list) else ("" if v is None else str(v))
    return f"{v} [{field.get('src', '?')}]" if v else f"? [{field.get('src', 'unknown')}]"


def table():
    out = []
    for f in sorted((OUT / "records").glob("*.json")):
        rec = json.loads(f.read_text())
        v = rec.get("video", {})
        n = v.get("n")
        trades = rec.get("trades") or []
        if not trades:
            out.append({"n": n, "trade": "none", "date": cell(v.get("session_date")),
                        "setup": rec.get("no_trade_reason", ""), "claimed_pnl": v.get("title_claim", ""),
                        "evidence": "accessed" if v.get("accessed") else "NOT ACCESSED"})
            continue
        for i, tr in enumerate(trades, 1):
            out.append({"n": n, "trade": i, "date": cell(tr.get("date") or v.get("session_date")),
                        "instrument": cell(tr.get("instrument")), "direction": cell(tr.get("direction")),
                        "timeframes": cell(tr.get("timeframes")), "setup": cell(tr.get("setup")),
                        "entry": cell(tr.get("entry")), "stop": cell(tr.get("stop")),
                        "target": cell(tr.get("target")), "exit": cell(tr.get("exit")),
                        "size": cell(tr.get("size_or_leverage")), "result": cell(tr.get("result")),
                        "r_multiple": (tr.get("r_multiple") or {}).get("value", ""),
                        "r_basis": (tr.get("r_multiple") or {}).get("src", ""),
                        "claimed_pnl": cell(tr.get("claimed_pnl")) or v.get("title_claim", ""),
                        "pnl_verified": cell(tr.get("pnl_verified")),
                        "mistakes": "; ".join(m if isinstance(m, str) else cell(m) for m in tr.get("mistakes", [])),
                        "evidence": tr.get("evidence_summary", "")})
    with open(OUT / "trades.csv", "w", newline="") as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} rows -> {OUT / 'trades.csv'}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "inventory":
        inventory()
    elif cmd == "prepare":
        prepare([int(x) for x in sys.argv[2:]])
    elif cmd == "table":
        table()
    else:
        sys.exit(__doc__)
