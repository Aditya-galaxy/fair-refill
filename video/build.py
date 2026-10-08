"""
Cut the film: each line's frame, held for as long as the line takes.

    python video/build.py          # after capture.py and narrate.py

Writes video/out/fair-refill-demo.mp4 (1920 x 1080, H.264 + AAC) and refuses
to finish if it runs to three minutes, which is the hackathon's limit.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
LIMIT = 180.0


def main() -> int:
    timeline = json.loads((OUT / "timeline.json").read_text())
    lines = timeline["lines"]
    listing = OUT / "frames.txt"
    with listing.open("w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(f"file '{(OUT / 'frames' / (line['frame'] + '.png')).as_posix()}'\nduration {line['duration']}\n")
        # The concat demuxer needs the last picture named once more.
        fh.write(f"file '{(OUT / 'frames' / (lines[-1]['frame'] + '.png')).as_posix()}'\n")
    film = OUT / "fair-refill-demo.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(OUT / "narration.wav"),
                    "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-c:a", "aac", "-b:a", "160k", "-t", f"{sum(line['duration'] for line in lines):.3f}",
                    "-movflags", "+faststart", str(film)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(film)],
                           check=True, capture_output=True, text=True)
    length = float(probe.stdout.strip())
    print(f"  {film.relative_to(HERE.parent)}: {int(length // 60)}:{length % 60:04.1f}, "
          f"{film.stat().st_size / 1e6:.1f} MB, voices: {timeline['engine']}")
    if length >= LIMIT:
        print("  That is at or over three minutes. Cut a segment from script.json and rebuild.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
