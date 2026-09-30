"""
ingest_video.py: turns a trading video into chart pictures + what's said, so its lessons can be studied.

    python research/tjr/ingest_video.py path/to/video.mp4 [more videos...]

For each video it writes research/tjr/raw/<name>/:
  shots/, sheets/  a picture every time the chart changes, and the same four to a page (frames.py)
  transcript.txt   what's said, with [mm:ss] timestamps
The raw folder is not committed: it's the video owner's content. Only our own notes
(research/tjr/notes/) and the rulebook (research/tjr/RULES.md) go into the repo.

Speech to text: uses Whisper (accurate) when its model can be downloaded, otherwise
PocketSphinx (built in, works offline, rougher: good for the gist, weak on jargon).
Needs: pip install imageio-ffmpeg pocketsphinx faster-whisper
"""
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

import frames

RAW = frames.RAW
RATE = 16000                      # 16 kHz mono: what speech models expect
CHUNK = 15                        # seconds of audio per transcript line (offline engine)


def audio_pcm(video: Path) -> bytes:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    out = subprocess.run([ffmpeg, "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", str(RATE),
                          "-f", "s16le", "-"], capture_output=True, check=True)
    return out.stdout


def stamp(seconds: float) -> str:
    return f"[{int(seconds // 60):02d}:{int(seconds % 60):02d}]"


def whisper_lines(video: Path):
    from faster_whisper import WhisperModel
    model = WhisperModel("small.en", device="cpu", compute_type="int8")     # downloads once (~500 MB)
    segments, _ = model.transcribe(str(video), vad_filter=True)
    return [f"{stamp(s.start)} {s.text.strip()}" for s in segments]


def sphinx_lines(pcm: bytes):
    from pocketsphinx import Decoder
    decoder = Decoder(samprate=RATE)
    step = CHUNK * RATE * 2                                                   # 2 bytes per sample
    lines = []
    for start in range(0, len(pcm), step):
        decoder.start_utt()
        decoder.process_raw(pcm[start:start + step], full_utt=True)
        decoder.end_utt()
        text = decoder.hyp().hypstr if decoder.hyp() else ""
        if text.strip():
            lines.append(f"{stamp(start / (RATE * 2))} {text.strip()}")
    return lines


def ingest(video: Path) -> Path:
    folder = frames.study(video)                                              # the chart pictures first (fast)
    try:
        lines, engine = whisper_lines(video), "whisper small.en (accurate)"
    except Exception as e:                                                    # model can't be downloaded here
        print(f"  Whisper unavailable ({type(e).__name__}); using the offline engine")
        lines, engine = sphinx_lines(audio_pcm(video)), "pocketsphinx (offline, rough: check jargon against the frames)"
    header = f"# {video.name}\n# speech-to-text: {engine}\n"
    (folder / "transcript.txt").write_text(header + "\n".join(lines) + "\n")
    print(f"  {video.name}: {len(lines)} transcript lines -> {folder / 'transcript.txt'}")
    return folder


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for name in sys.argv[1:]:
        ingest(Path(name))
