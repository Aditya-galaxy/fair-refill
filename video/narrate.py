"""
Give the film its voices.

    python video/narrate.py --engine say      # the Mac's own voices: free, for a timing draft
    GEMINI_API_KEY=… python video/narrate.py  # hosted voices, for the real cut
    FAIR_REFILL_VOICE_PROJECT=<project> python video/narrate.py --engine cloud
                                              # the same Gemini voices from a hosted
                                              # speech service, with your signed-in account

Three voices: a narrator over the title cards, the person asking, and the
assistant. The assistant only ever reads video/out/answers.json, which
capture.py wrote from the add-on's real answers.

The hosted voices allow ten requests a day on the free tier, so consecutive
turns that share a `group` in script.json are spoken in one two-voice request.
A group's audio is then shared out between its lines by length of text, which
and each cut is moved to the nearest real pause, so a picture changes
between two speakers. A group
already rendered is kept unless --force is given, so a run cut off by the
quota resumes.

The cloud engine has no daily cap, so it renders one line at a time: each
line's audio is exactly that line, with nothing to share out between speakers.

Writes video/out/narration.wav and video/out/timeline.json (what build.py
needs: each line's picture and how long it stays).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
AUDIO = OUT / "audio"
MODEL = os.environ.get("FAIR_REFILL_TTS_MODEL", "gemini-2.5-flash-preview-tts")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RATE, WIDTH = 24_000, 2            # Gemini returns 16-bit mono PCM at 24 kHz
GAP = 0.35                         # between a question and its answer
CLOUD_TTS = "https://texttospeech.googleapis.com/v1/text:synthesize"
CLOUD_MODEL = os.environ.get("FAIR_REFILL_CLOUD_TTS_MODEL", "gemini-2.5-flash-tts")
# How each voice is asked to read, on the cloud engine (one line at a time).
# A natural pace, not a slow one: the film has three minutes, and the
# assistant's answers are long because they carry their conditions.
STYLE = {"narrator": "Read this clearly, at a natural conversational pace.",
         "person": "Ask this plainly, as an older adult speaking to a voice assistant, at a natural pace.",
         "assistant": "Answer warmly and clearly, as a voice assistant, at a natural conversational pace."}
SPEAKING_RATE = float(os.environ.get("FAIR_REFILL_SPEAKING_RATE", "1.1"))


def account_token() -> str:
    """An access token for the signed-in account. Never printed."""
    return subprocess.run(["gcloud", "auth", "print-access-token"], check=True, capture_output=True,
                          text=True).stdout.strip()


def spoken(text: str) -> str:
    """Units as words, so no voice reads "mg" as two letters."""
    text = re.sub(r"(\d)\s*mcg\b", r"\1 micrograms", text)
    text = re.sub(r"(\d)\s*mg/ml\b", r"\1 milligrams per millilitre", text)
    text = re.sub(r"(\d)\s*mg\b", r"\1 milligrams", text)
    return text.replace("Alexa+", "Alexa Plus")


def lines_of(script: dict, answers: dict) -> list[dict]:
    """Every spoken line in order: who says it, over which frame, in which group."""
    out = []
    for seg in script["segments"]:
        if seg["kind"] == "card":
            out.append({"id": seg["id"], "who": "narrator", "text": spoken(seg["say"]), "frame": seg["id"],
                        "group": seg["id"], "pause": seg.get("pause_after", 0.0)})
        else:
            out.append({"id": seg["id"] + ".ask", "who": "person", "text": spoken(seg["ask"]),
                        "frame": seg["id"] + "-heard", "group": seg["group"], "pause": GAP})
            out.append({"id": seg["id"] + ".answer", "who": "assistant", "text": spoken(answers[seg["id"]]["speech"]),
                        "frame": seg["id"] + "-answered", "group": seg["group"], "pause": seg.get("pause_after", 0.0)})
    return out


def write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(WIDTH)
        fh.setframerate(RATE)
        fh.writeframes(pcm)


def seconds(pcm: bytes) -> float:
    return len(pcm) / (RATE * WIDTH)


def silence(duration: float) -> bytes:
    return b"\x00" * (int(RATE * duration) * WIDTH)


def pauses(pcm: bytes, quiet: int = 350, shortest: float = 0.18) -> list[tuple[int, float]]:
    """Each pause in the audio as (byte offset of its middle, its length in
    seconds): runs of near-silence at least `shortest` seconds long."""
    import array
    samples = array.array("h", pcm[:len(pcm) // WIDTH * WIDTH])
    window = RATE // 50                                   # 20 ms
    found, run_start = [], None
    for i in range(0, len(samples) - window, window):
        loud = max(abs(v) for v in samples[i:i + window]) > quiet
        if not loud and run_start is None:
            run_start = i
        elif loud and run_start is not None:
            if (i - run_start) / RATE >= shortest:
                found.append(((run_start + i) // 2 * WIDTH, (i - run_start) / RATE))
            run_start = None
    return found


def snap(estimate: int, quiet_points: list[tuple[int, float]], after: int, within: float = 3.0) -> int:
    """Move a cut made by length of text to a real pause nearby, so the picture
    changes between two speakers and not inside a word. Of the pauses within
    reach, the longest wins: a change of speaker pauses longer than the gap
    between one person's sentences. A line is at least 0.7 s of speech, so a
    pause sooner than that after the last cut (the silence a clip opens with,
    say) isn't the one."""
    earliest = after + int(0.7 * RATE) * WIDTH
    near = [(q, length) for q, length in quiet_points
            if q >= earliest and abs(q - estimate) <= within * RATE * WIDTH]
    if not near:
        return max(estimate, earliest)
    return max(near, key=lambda p: (round(p[1], 1), -abs(p[0] - estimate)))[0]


def say(text: str, voice: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        aiff, raw = Path(tmp) / "line.aiff", Path(tmp) / "line.raw"
        subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True)
        subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-ar", str(RATE), "-ac", "1", "-f", "s16le", str(raw)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return raw.read_bytes()


def gemini(group: list[dict], voices: dict[str, str], key: str) -> bytes:
    """One request for a whole group. The key rides in a header and is never printed."""
    speakers = sorted({line["who"] for line in group})
    if len(speakers) == 1:
        text = "Read this in a calm, clear, unhurried voice:\n\n" + "\n\n".join(line["text"] for line in group)
        speech = {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voices[speakers[0]]}}}
    else:
        names = {"person": "Person", "assistant": "Assistant"}
        text = ("Read this conversation. Person asks plainly, as an older adult speaking to a voice assistant. "
                "Assistant answers warmly and clearly, at an unhurried pace.\n\n"
                + "\n".join(f"{names[line['who']]}: {line['text']}" for line in group))
        speech = {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
            {"speaker": names[w], "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voices[w]}}}
            for w in speakers]}}
    body = {"contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": speech}}
    for attempt in range(4):
        r = httpx.post(ENDPOINT.format(model=MODEL), headers={"x-goog-api-key": key}, json=body, timeout=180)
        if r.status_code == 200:
            parts = r.json()["candidates"][0]["content"]["parts"]
            return base64.b64decode(next(p["inlineData"]["data"] for p in parts if "inlineData" in p))
        if r.status_code == 429 and "PerDay" in r.text:
            raise SystemExit("  The voice model's daily quota is used up. Run again tomorrow; "
                             "finished groups are kept.")
        if r.status_code not in (429, 500, 502, 503, 504) or attempt == 3:
            raise SystemExit(f"  The voice model answered {r.status_code}.")
        time.sleep(10 * (attempt + 1))
    raise AssertionError("unreachable")


def cloud(line: dict, voices: dict[str, str], project: str, token: str) -> bytes:
    """One line, in that speaker's Gemini voice, from the hosted speech service."""
    body = {"input": {"prompt": STYLE[line["who"]], "text": line["text"]},
            "voice": {"languageCode": "en-US", "name": voices[line["who"]], "modelName": CLOUD_MODEL},
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": RATE, "speakingRate": SPEAKING_RATE}}
    for attempt in range(4):
        r = httpx.post(CLOUD_TTS, json=body, timeout=180,
                       headers={"Authorization": f"Bearer {token}", "x-goog-user-project": project})
        if r.status_code == 200:
            audio = base64.b64decode(r.json()["audioContent"])
            return audio[44:] if audio[:4] == b"RIFF" else audio      # LINEAR16 comes as a WAV file
        if r.status_code not in (429, 500, 502, 503, 504) or attempt == 3:
            raise SystemExit(f"  Text-to-Speech answered {r.status_code}.")
        time.sleep(10 * (attempt + 1))
    raise AssertionError("unreachable")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", choices=("gemini", "cloud", "say"), default="gemini")
    ap.add_argument("--force", action="store_true", help="render groups again even if their audio exists")
    args = ap.parse_args()

    script = json.loads((HERE / "script.json").read_text(encoding="utf-8"))
    answers_path = OUT / "answers.json"
    if not answers_path.exists():
        print("Run video/capture.py first: the assistant reads the answers it records.")
        return 1
    lines = lines_of(script, json.loads(answers_path.read_text(encoding="utf-8")))
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if args.engine == "gemini" and not key:
        print("Set GEMINI_API_KEY, or use --engine cloud or --engine say.")
        return 1
    project = os.environ.get("FAIR_REFILL_VOICE_PROJECT", "").strip()
    if args.engine == "cloud" and not project:
        print("Set FAIR_REFILL_VOICE_PROJECT to the project to bill the voices to.")
        return 1
    token = account_token() if args.engine == "cloud" else ""
    audio = AUDIO / args.engine
    audio.mkdir(parents=True, exist_ok=True)

    groups: dict[str, list[dict]] = {}
    for line in lines:
        groups.setdefault(line["group"], []).append(line)

    track, timeline, at = b"", [], 0.0
    for name, group in groups.items():
        if args.engine == "say":
            pieces = [say(line["text"], script["say_voices"][line["who"]]) for line in group]
        elif args.engine == "cloud":
            pieces = []
            for line in group:
                path, fingerprint = audio / f"{line['id']}.pcm", audio / f"{line['id']}.txt"
                said = json.dumps([line["who"], line["text"], CLOUD_MODEL, STYLE[line["who"]], SPEAKING_RATE])
                if path.exists() and not args.force and fingerprint.exists() and fingerprint.read_text() == said:
                    print(f"  {line['id']}: kept")
                else:
                    print(f"  {line['id']}: asking the voice model…", flush=True)
                    path.write_bytes(cloud(line, script["voices"], project, token))
                    fingerprint.write_text(said)
                pieces.append(path.read_bytes())
        else:
            path = audio / f"{name}.pcm"
            fingerprint = audio / f"{name}.txt"
            text = json.dumps([[line["who"], line["text"]] for line in group])
            if path.exists() and not args.force and fingerprint.exists() and fingerprint.read_text() == text:
                print(f"  {name}: kept")
            else:
                print(f"  {name}: asking the voice model…", flush=True)
                path.write_bytes(gemini(group, script["voices"], key))
                fingerprint.write_text(text)
            whole = path.read_bytes()
            total = sum(len(line["text"]) for line in group)
            quiet_points = pauses(whole)
            cuts, start, said = [], 0, 0
            for line in group[:-1]:
                said += len(line["text"])
                end = snap(int(len(whole) * said / total) // WIDTH * WIDTH, quiet_points, after=start)
                cuts.append(whole[start:end])
                start = end
            pieces = [*cuts, whole[start:]]
        for line, pcm in zip(group, pieces, strict=True):
            # In a hosted group the pause between lines is already in the audio.
            pad = line["pause"] if args.engine != "gemini" or line is group[-1] else 0.0
            pcm += silence(pad)
            timeline.append({"id": line["id"], "who": line["who"], "frame": line["frame"],
                             "start": round(at, 2), "duration": round(seconds(pcm), 3)})
            at += seconds(pcm)
            track += pcm

    write_wav(OUT / "narration.wav", track)
    (OUT / "timeline.json").write_text(json.dumps({"engine": args.engine, "lines": timeline}, indent=1))
    words = sum(len(line["text"].split()) for line in lines)
    print(f"\n  {len(lines)} lines, {words} words, {int(at // 60)}:{at % 60:04.1f} "
          f"({'under' if at < 180 else 'OVER'} the 3-minute limit)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
