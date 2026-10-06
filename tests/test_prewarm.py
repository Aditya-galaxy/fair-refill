"""
Pre-warming, against the same recorded prices: after a round, the questions
people ask most are answered without going to any source.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from fair_refill import prewarm
from fair_refill.http import Http, ReplayTransport
from fair_refill.service import PriceCheck

FIXTURES = Path(__file__).parent / "fixtures" / "responses.json"
RECORDED = ["atorvastatin", "Lipitor 20", "metformin 500", "xyzzy"]


class Counting(ReplayTransport):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.requests = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        return super().handle_request(request)


class Offline(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)


def _check(transport: httpx.BaseTransport, cache: Path, refresh_after: float = 1.0) -> PriceCheck:
    return PriceCheck(Http(httpx.Client(transport=transport), cache_dir=cache, refresh_after=refresh_after))


@pytest.fixture
def warmed(tmp_path):
    done = prewarm.warm(_check(ReplayTransport(FIXTURES), tmp_path), RECORDED)
    return tmp_path, done


def test_a_round_prices_every_strength_it_can_compare(warmed):
    _, done = warmed
    assert done.medicines == len(RECORDED)
    assert done.failed == ()
    # atorvastatin 10, 20, 40 and 80; Lipitor 20; metformin 500 regular and
    # extended-release. Atorvastatin's liquid is warmed but isn't a price
    # comparison, and the nonsense word finds nothing.
    assert done.priced == 7


@pytest.mark.parametrize("text", ["atorvastatin 20 mg", "Lipitor 20", "lipitor 20", "metformin 500"])
def test_after_a_round_the_answer_needs_no_source(warmed, text):
    cache, _ = warmed
    result = _check(Offline(), cache).ask(text, you_pay=40.0)
    assert result.kind in ("answer", "choose"), result.speech


def test_a_follow_up_by_id_needs_no_source_either(warmed):
    cache, _ = warmed
    check = _check(Offline(), cache)
    asked = check.ask("atorvastatin")
    assert asked.kind == "choose"
    for offered in asked.choices:
        drug = check.rx.drug(offered.rxcui)
        assert drug is not None
        assert check.check(drug, 30).kind == "answer"


def test_a_cold_question_still_says_when_a_source_is_down(tmp_path):
    assert _check(Offline(), tmp_path).ask("atorvastatin 20 mg").kind == "unavailable"


def test_a_source_being_down_fails_that_medicine_and_not_the_round(tmp_path):
    done = prewarm.warm(_check(Offline(), tmp_path), ["atorvastatin", "metformin"])
    assert done.priced == 0
    assert set(done.failed) == {"atorvastatin", "metformin"}


def test_a_second_round_fetches_only_what_is_getting_old(warmed):
    cache, _ = warmed
    again = Counting(FIXTURES)
    prewarm.warm(_check(again, cache, prewarm.REFRESH_AFTER), RECORDED)
    assert again.requests == 0, "everything was just fetched; nothing is due"

    # Seven hours on, prices (kept 12 hours) are past half their life and are
    # fetched again; drug names (kept a week) are not.
    for path in cache.glob("*.json"):
        entry = json.loads(path.read_text(encoding="utf-8"))
        entry["at"] = time.time() - 7 * 3600
        path.write_text(json.dumps(entry), encoding="utf-8")
    later = Counting(FIXTURES)
    prewarm.warm(_check(later, cache, prewarm.REFRESH_AFTER), RECORDED)
    assert later.requests > 0
    assert _check(Offline(), cache).ask("atorvastatin 20 mg").kind == "answer"


def test_it_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("FAIR_REFILL_PREWARM", "0")
    assert prewarm.in_background() is None
