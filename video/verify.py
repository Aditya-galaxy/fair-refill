"""
Check that the voices said what they were given to say.

    GEMINI_API_KEY=… python video/verify.py
    FAIR_REFILL_GCP_PROJECT=<project> python video/verify.py    # for --engine cloud takes, via Vertex AI

Hosted voice models slip: in two takes of one exchange, one said "three months
at months" and the next dropped "your deductible or" from a sentence. Nobody
watching would catch that, and the film would be putting words in the add-on's
mouth. So every group of lines is transcribed by a second model and compared,
word by word, with the text it was rendered from. Any stretch of two or more
words that is missing, added or different fails the group, and the script says
which take to delete and render again.

The transcriber makes its own mistakes (it hears "RX Pass" for RxPass), so
single-word differences are listed but don't fail a group.
"""

from __future__ import annotations

import base64
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from narrate import AUDIO, OUT, RATE, gcloud_token, lines_of  # noqa: E402

sys.path.insert(0, str(HERE.parent))

from fair_refill.brain import _words_to_digits  # noqa: E402

MODEL = os.environ.get("FAIR_REFILL_CHECK_MODEL", "gemini-3.1-flash-lite")
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
def words(text: str) -> list[str]:
    """Words as a listener would count them: case, punctuation and the way a
    number, a price or a unit is written don't matter."""
    text = _words_to_digits(text.lower())                       # "sixty-five" and "65" are one word
    text = re.sub(r"\$\s?(\d[\d,]*(?:\.\d+)?)", r"\1 dollars", text)   # "$40" and "40 dollars"
    text = text.replace("%", " percent ")
    text = re.sub(r"\bmg\b|\bmilligram\b", "milligrams", text)
    text = re.sub(r"\brx pass\b", "rxpass", text)
    text = re.sub(r"(\d),(\d)", r"\1\2", text)
    text = re.sub(r"[^\w.\- ]", " ", text).replace("-", " ")
    return [w.strip(".") for w in text.split() if w.strip(".")]


# Spelled for the transcriber, which otherwise writes "a torvastatin" for the
# way a voice says the word's first vowel. It still has to hear the name said.
NAMES = ("atorvastatin", "Lipitor", "metformin", "Eliquis", "Ozempic", "Cost Plus Drugs", "RxPass", "Medicare",
         "Fair Refill", "Alexa Plus", "MCP")

VERTEX_MODEL = os.environ.get("FAIR_REFILL_VERTEX_CHECK_MODEL", "gemini-2.5-flash")


def transcribe(pcm: bytes, key: str, project: str = "") -> str:
    with tempfile.TemporaryDirectory() as tmp:
        raw, mp3 = Path(tmp) / "a.pcm", Path(tmp) / "a.mp3"
        raw.write_bytes(pcm)
        subprocess.run(["ffmpeg", "-y", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", str(raw), "-b:a", "96k",
                        str(mp3)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        audio = base64.b64encode(mp3.read_bytes()).decode()
    body = {"contents": [{"parts": [
        {"text": "Transcribe exactly what is said, word for word, with no speaker names and no corrections. "
                 "Medicine and product names that may be said: " + ", ".join(NAMES) + "."},
        {"inlineData": {"mimeType": "audio/mp3", "data": audio}}]}], "generationConfig": {"temperature": 0}}
    for attempt in range(6):
        if project:
            body["contents"][0]["role"] = "user"
            url = (f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/"
                   f"publishers/google/models/{VERTEX_MODEL}:generateContent")
            r = httpx.post(url, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=300)
        else:
            r = httpx.post(ENDPOINT, headers={"x-goog-api-key": key}, json=body, timeout=300)
        if r.status_code not in (429, 500, 502, 503, 504) or attempt == 5:
            break
        time.sleep(15 * (attempt + 1))                  # a shared quota: wait it out
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def differences(expected: str, heard: str) -> list[tuple[str, str, str]]:
    """(kind, what was written, what was heard) for every stretch that differs."""
    a, b = words(expected), words(heard)
    return [(op, " ".join(a[i1:i2]), " ".join(b[j1:j2]))
            for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
            if op != "equal"]


def serious(diff: tuple[str, str, str]) -> bool:
    _, written, heard = diff
    if written.replace(" ", "") == heard.replace(" ", ""):
        return False                                # "co pay" for "copay": the same sounds, spaced differently
    return max(len(written.split()), len(heard.split())) >= 2


def main() -> int:
    project = os.environ.get("FAIR_REFILL_GCP_PROJECT", "").strip()
    key = gcloud_token() if project else os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("Set GEMINI_API_KEY, or FAIR_REFILL_GCP_PROJECT to check cloud takes through Vertex AI.")
        return 1
    engine = "cloud" if project else "gemini"
    script = json.loads((HERE / "script.json").read_text(encoding="utf-8"))
    lines = lines_of(script, json.loads((OUT / "answers.json").read_text(encoding="utf-8")))
    groups: dict[str, list[dict]] = {}
    for line in lines:
        # Cloud takes are one line each, so each is checked on its own.
        groups.setdefault(line["id"] if engine == "cloud" else line["group"], []).append(line)

    failed = []
    for name, group in groups.items():
        path = AUDIO / engine / f"{name}.pcm"
        if not path.exists():
            print(f"  {name}: not rendered yet")
            failed.append(name)
            continue
        found = differences(" ".join(line["text"] for line in group), transcribe(path.read_bytes(), key, project))
        bad = [d for d in found if serious(d)]
        small = f" ({len(found) - len(bad)} one-word differences)" if found else ""
        print(f"  {name}: {'FAIL' if bad else 'ok'}{small}")
        for kind, written, heard in found:
            mark = "!!" if serious((kind, written, heard)) else "  "
            print(f"    {mark} {kind:<8} written: {written!r:<40} heard: {heard!r}")
        if bad:
            failed.append(name)
    if failed:
        print("\n  Render again: " + " ".join(f"rm video/out/audio/{engine}/{n}.pcm;" for n in failed)
              + f" python video/narrate.py --engine {engine}")
        return 1
    print("\n  Every group says what it was given.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
