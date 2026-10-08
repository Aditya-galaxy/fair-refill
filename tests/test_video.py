"""The demo film's pipeline: what the voices are given, where pictures change,
and the check that the voices said it."""

from __future__ import annotations

import array
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video"))

import narrate  # noqa: E402
import verify  # noqa: E402

SCRIPT = json.loads((ROOT / "video" / "script.json").read_text(encoding="utf-8"))


def tone(seconds: float) -> bytes:
    return array.array("h", [8000] * int(narrate.RATE * seconds)).tobytes()


def test_the_assistant_only_reads_the_add_ons_recorded_answers():
    answers = {s["id"]: {"speech": f"ANSWER {s['id']} 20 mg"} for s in SCRIPT["segments"] if s["kind"] == "turn"}
    lines = narrate.lines_of(SCRIPT, answers)
    said = [line for line in lines if line["who"] == "assistant"]
    assert said and all(line["text"].startswith("ANSWER ") and line["text"].endswith("20 milligrams") for line in said)
    assert [line["frame"] for line in lines if line["id"].startswith("atorvastatin")] == \
        ["atorvastatin-heard", "atorvastatin-answered"]
    # No script segment carries words for the assistant.
    assert not any("answer" in s or ("say" in s and s["kind"] == "turn") for s in SCRIPT["segments"])


def test_units_are_spoken_as_words():
    assert narrate.spoken("atorvastatin 20 mg tablet, Alexa+") == "atorvastatin 20 milligrams tablet, Alexa Plus"
    assert narrate.spoken("levothyroxine 50 mcg") == "levothyroxine 50 micrograms"


def test_a_cut_moves_to_the_longest_pause_nearby_not_the_first():
    # 2 s speech, a 0.3 s breath, 2 s speech, a 0.8 s change of speaker, 5 s speech.
    pcm = tone(2) + narrate.silence(0.3) + tone(2) + narrate.silence(0.8) + tone(5)
    quiet = narrate.pauses(pcm)
    assert [round(length, 1) for _, length in quiet] == [0.3, 0.8]
    estimate = int(3.0 * narrate.RATE) * narrate.WIDTH          # by length of text: nearer the breath
    cut = narrate.snap(estimate, quiet, after=0) / (narrate.RATE * narrate.WIDTH)
    assert 4.3 < cut < 5.1                                       # inside the change of speaker


def test_a_cut_never_lands_in_the_silence_a_clip_opens_with():
    pcm = narrate.silence(0.4) + tone(2) + narrate.silence(0.5) + tone(3)
    cut = narrate.snap(int(0.5 * narrate.RATE) * narrate.WIDTH, narrate.pauses(pcm), after=0)
    assert cut / (narrate.RATE * narrate.WIDTH) > 2.0


def test_the_same_words_written_differently_are_not_a_difference():
    written = "Americans aged sixty-five pay $40 a month for atorvastatin 20 mg. Amazon RxPass covers it."
    heard = "americans aged 65 pay 40 dollars a month for atorvastatin 20 milligrams, Amazon RX Pass covers it"
    assert verify.differences(written, heard) == []


def test_a_dropped_phrase_fails_and_a_misheard_word_does_not():
    written = "Cash prices usually don't count toward your deductible or Medicare's yearly limit."
    dropped = verify.differences(written, "Cash prices usually don't count toward Medicare's yearly limit.")
    assert any(verify.serious(d) for d in dropped)
    slip = verify.differences("prescribes three months at once", "prescribes 3 months at months")
    assert slip and not any(verify.serious(d) for d in slip)     # one word: listed, for a person to judge
    misheard = verify.differences("weren't open to entrants", "weren't open to entrance")
    assert misheard and not any(verify.serious(d) for d in misheard)


def test_the_page_can_carry_a_conversation_in_its_link():
    page = (ROOT / "fair_refill" / "simulator.html").read_text(encoding="utf-8")
    assert 'linked.getAll("ask")' in page and "document.body.dataset.asked" in page
