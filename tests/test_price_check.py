"""
Fair Refill, tested on real prices.

The end-to-end tests replay responses recorded from RxNorm, CMS NADAC and
Cost Plus Drugs (tools/record_fixtures.py), so they check real behaviour
without touching the network. The pure tests pin the rules a price answer
must keep for the person hearing it.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from fair_refill import medicare, rxpass
from fair_refill.compare import CASH_CAVEAT, assess, cannot_compare, comparable_form, medicare_price, money
from fair_refill.costplus import Quote
from fair_refill.http import replay_client
from fair_refill.nadac import NadacPrice
from fair_refill.rxnorm import Drug, split_query
from fair_refill.service import PriceCheck

FIXTURES = Path(__file__).parent / "fixtures" / "responses.json"
RECORDED_ON = date(2026, 10, 6)       # some answers depend on the date; the prices are that week's


@pytest.fixture(scope="module")
def check():
    return PriceCheck(replay_client(FIXTURES), today=RECORDED_ON)


# ── what's said has to be safe to hear ───────────────────────────────────────

JARGON = re.compile(r"\b(NADAC|NDC|RxCUI|rxcui|SCD|SBD|RxNorm|acquisition)\b")
DANGEROUS = re.compile(r"\b(stop taking|skip|switch to|instead of your|double up|take less|half)\b", re.I)
NEXT_STEP = re.compile(r"(pharmacist|your plan|doctor)", re.I)

ANSWERS = ["atorvastatin 20 mg", "Lipitor 20", "lipiter 20", "eliquis 5 mg",
           "metformin 500 mg extended release", "albuterol inhaler", "lisinopril 10 mg",
           "Ozempic", "Tradjenta", "Linzess 145 mcg", "Enbrel"]


@pytest.mark.parametrize("text", ANSWERS)
def test_every_answer_is_plain_safe_and_ends_with_a_next_step(check, text):
    r = check.ask(text)
    assert r.kind == "answer", r.speech
    assert not JARGON.search(r.speech), r.speech
    assert not DANGEROUS.search(r.speech), r.speech
    sentences = [x for x in re.split(r"(?<=[.?!])\s+", r.speech) if x]
    assert NEXT_STEP.search(" ".join(sentences[-2:])), f"no next step at the end: {r.speech}"
    assert len(re.findall(r"[.?!](\s|$)", r.speech)) <= 5          # short enough to listen to


# ── end to end, on recorded real data ────────────────────────────────────────

def test_generic_is_priced_against_what_pharmacies_pay(check):
    r = check.ask("atorvastatin 20 mg")
    assert "Pharmacies pay about 84 cents a month for atorvastatin 20 mg tablet" in r.speech
    assert "Cost Plus Drugs sells it for $5.41 a month plus shipping" in r.speech
    assert r.finding.sources[0].startswith("CMS NADAC, 2026-")


def test_overpaying_is_measured_against_a_price_anyone_can_buy_at(check):
    r = check.ask("atorvastatin 20 mg", you_pay=40.0)
    # $40 - $5.41 at Cost Plus, not $40 - $5 at RxPass, which needs Prime and skips insurance
    assert r.finding.overpaying_by == pytest.approx(40 - 5.41, abs=0.01)
    assert "paying about $35 a month more than you need to" in r.speech
    assert "They're allowed to tell you" in r.speech


def test_a_brand_is_compared_with_its_own_generic_as_a_question(check):
    r = check.ask("Lipitor 20")
    assert "$572 a month for Lipitor 20 mg tablet" in r.speech
    assert "84 cents for the generic, atorvastatin 20 mg tablet" in r.speech
    assert "Ask your pharmacist or doctor whether the generic is right for you" in r.speech


def test_a_misspelling_is_corrected_and_said_back(check):
    r = check.ask("lipiter 20")
    assert r.corrected == "lipitor"
    assert r.speech.startswith("I found Lipitor 20 mg tablet.")


def test_a_brand_without_a_generic_gets_medicare_facts(check):
    r = check.ask("eliquis 5 mg")
    assert "negotiated price for Eliquis is $231 for a 30-day supply this year, down from $521" in r.speech
    assert "$2,100" in r.speech


def test_a_cash_price_always_comes_with_its_catch(check):
    """Money paid outside insurance usually doesn't count toward a deductible
    or Medicare's yearly limit. Whoever hears a cash price hears that too."""
    for text, you_pay in (("atorvastatin 20 mg", None), ("atorvastatin 20 mg", 40.0), ("Lipitor 20", None)):
        speech = check.ask(text, you_pay=you_pay).speech
        assert "Cost Plus Drugs sells it" in speech
        assert CASH_CAVEAT in speech, speech
    assert CASH_CAVEAT not in check.ask("eliquis 5 mg").speech       # no cash price said, so no catch to add


def test_a_price_that_starts_in_january_is_said_as_coming(check):
    r = check.ask("Tradjenta")
    assert r.speech.startswith("Pharmacies pay about $504 a month for Tradjenta 5 mg tablet now.")
    assert ("From January 2027, Medicare's negotiated price for Tradjenta is about $78 for a typical 30-day "
            "supply, down from a list price of $488.") in r.speech
    assert r.speech.endswith("Ask your plan what you'll pay from January.")
    assert "this year" not in r.speech
    assert r.finding.sources == ("CMS negotiated prices 2027",)


def test_a_negotiated_injection_is_answered_for_the_brand_without_asking_which_pen(check):
    r = check.ask("Ozempic")
    assert r.kind == "answer" and r.finding.title == "Ozempic"
    assert "Ozempic is about $274 for a typical 30-day supply" in r.speech
    assert r.choices == ()                 # no strength was picked, so none is there to save
    r = check.ask("Enbrel")
    assert "negotiated price for Enbrel is $2,355 for a 30-day supply this year" in r.speech


def test_micrograms_find_what_rxnorm_writes_in_milligrams(check):
    assert check.ask("Linzess 145 mcg").finding.title == "Linzess 0.145 mg capsule"
    r = check.ask("levothyroxine 50 mcg")
    assert r.kind == "choose"
    assert r.speech == "Which levothyroxine do you take: 0.05 mg/ml liquid, 0.05 mg tablet, or 0.05 mg capsule?"


def test_an_ambiguous_medicine_is_a_short_question(check):
    r = check.ask("metformin 500")
    assert r.kind == "choose"
    assert r.speech == "Which metformin 500 mg do you take: extended-release tablet, or regular tablet?"
    assert len(r.choices) == 2


def test_choices_never_exceed_five(check):
    r = check.ask("atorvastatin")
    assert r.kind == "choose" and len(r.choices) <= 5


def test_forms_it_cannot_price_are_said_plainly_without_a_pointless_question(check):
    r = check.ask("albuterol inhaler")
    assert r.kind == "answer" and not r.finding.comparable
    assert "not yet for inhalers" in r.speech


def test_unknown_medicine(check):
    r = check.ask("xyzzy")
    assert r.kind == "not_found" and "name on the label" in r.speech


# ── understanding what people say ────────────────────────────────────────────

@pytest.mark.parametrize("said, expected", [
    ("atorvastatin 20mg", ("atorvastatin", "20 mg")),
    ("Lipitor 20", ("Lipitor", "20")),
    ("my metformin 500 mg tablets", ("metformin", "500 mg")),
    ("eliquis", ("eliquis", None)),
])
def test_split_query(said, expected):
    assert split_query(said) == expected


@pytest.mark.parametrize("name, spoken", [
    ("atorvastatin 20 MG Oral Tablet", "atorvastatin 20 mg tablet"),
    ("atorvastatin 20 MG Oral Tablet [Lipitor]", "Lipitor 20 mg tablet"),
    ("24 HR metformin hydrochloride 500 MG Extended Release Oral Tablet",
     "metformin 500 mg extended-release tablet"),
    ("200 ACTUAT albuterol 0.09 MG/ACTUAT Metered Dose Inhaler", "albuterol 90 mcg per puff inhaler, 200 puffs"),
])
def test_spoken_names(name, spoken):
    assert Drug("1", name, "SBD" if "[" in name else "SCD").spoken == spoken


def test_product_specific_inhalers_keep_their_family():
    d = Drug("1", "NDA020983 200 ACTUAT albuterol 0.09 MG/ACTUAT Metered Dose Inhaler", "SCD", "Ventolin")
    assert d.spoken == "albuterol 90 mcg per puff inhaler, Ventolin type, 200 puffs"


def test_ingredients_and_form():
    d = Drug("1", "amlodipine 5 MG / olmesartan medoxomil 20 MG Oral Tablet", "SCD")
    assert d.ingredients == frozenset({"amlodipine", "olmesartan"})
    assert d.form == "tablet"


# ── the pure assessment ──────────────────────────────────────────────────────

@pytest.mark.parametrize("x, said", [(0.84, "84 cents"), (5.0, "$5"), (5.41, "$5.41"), (231.0, "$231"),
                                     (2100.0, "$2,100")])
def test_money_is_said_the_way_people_say_it(x, said):
    assert money(x) == said


GENERIC = Drug("617310", "atorvastatin 20 MG Oral Tablet", "SCD")
COST = NadacPrice(0.028, 0.0276, 0.028, "EA", 68, "2026-09-23", None)
CASH = Quote("67877051210", 5.41, 30, "https://example")


def _assess(you_pay=None, cash=CASH):
    return assess(asked=GENERIC, generic=GENERIC, quantity=30, asked_cost=COST, generic_cost=COST,
                  cash=cash, you_pay=you_pay)


def test_small_gaps_are_not_worth_worrying_someone_about():
    assert _assess(you_pay=7.0).overpaying_by is None        # $1.59 over: not worth a trip
    assert _assess(you_pay=9.0).overpaying_by == pytest.approx(3.59)


def test_rxpass_alone_never_says_someone_is_overpaying_without_its_conditions():
    f = _assess(you_pay=40.0, cash=None)
    assert "with Prime, outside insurance" in f.speech


def test_rxpass_conditions_are_carried():
    assert rxpass.may_cover(frozenset({"atorvastatin"}), "tablet")
    assert not rxpass.may_cover(frozenset({"atorvastatin"}), "extended-release tablet")
    assert any("Medicare" in c for c in rxpass.CAVEATS)


def test_comparable_forms():
    assert comparable_form("tablet") and comparable_form("extended-release capsule")
    assert not comparable_form("inhaler") and not comparable_form("liquid")
    assert not cannot_compare(Drug("1", "albuterol 5 MG/ML Inhalation Solution", "SCD")).comparable


def test_negotiated_prices_are_cms_figures():
    assert medicare.negotiated_for("Eliquis", RECORDED_ON).price_30_day == 231.00
    assert medicare.negotiated_for("novolog", RECORDED_ON).price_30_day == 119.00
    assert medicare.negotiated_for("Lipitor", RECORDED_ON) is None
    assert medicare.PART_D_CAP == 2100
    assert len(medicare.NEGOTIATED_2027) == 15
    coming = {n.brand: (n.price_30_day, n.list_price_30_day) for n in medicare.NEGOTIATED_2027}
    assert coming["Ozempic / Rybelsus / Wegovy"] == (274, 959)
    assert coming["Breo Ellipta"] == (67, 397)
    assert coming["Pomalyst"] == (8650, 21744)


def test_a_negotiated_price_is_coming_until_its_first_day_and_current_for_its_first_year():
    assert medicare.negotiated_for("Ozempic", date(2026, 12, 31)) is None
    assert medicare.upcoming_for("Ozempic", date(2026, 12, 31)).price_30_day == 274.00
    assert medicare.upcoming_for("Ozempic", date(2027, 1, 1)) is None
    assert medicare.negotiated_for("Wegovy", date(2027, 1, 1)).price_30_day == 274.00
    # CMS raises each price with inflation after its first year, so last
    # year's figure is not said as this year's.
    assert medicare.negotiated_for("Eliquis", date(2027, 1, 1)) is None


def test_open_enrollment_is_mentioned_only_while_it_is_open():
    tradjenta = Drug("1", "linagliptin 5 MG Oral Tablet [Tradjenta]", "SBD")
    before, during = medicare_price(tradjenta, date(2026, 10, 14)), medicare_price(tradjenta, date(2026, 10, 15))
    assert "open enrollment" not in before.speech
    assert "Medicare open enrollment runs until December 7" in during.speech
    assert "open enrollment" not in medicare_price(tradjenta, date(2026, 12, 8)).speech
    assert medicare_price(Drug("1", "atorvastatin 20 MG Oral Tablet [Lipitor]", "SBD"), RECORDED_ON) is None


def test_replay_refuses_to_go_online():
    http = replay_client(FIXTURES)
    with pytest.raises(AssertionError, match="no recorded response"):
        http.get("https://rxnav.nlm.nih.gov/REST/drugs.json", {"name": "never-recorded"})


class _FakeHttp:
    def __init__(self, payload):
        self.payload = payload

    def get(self, url, params=None):
        return self.payload


def test_a_cash_price_counts_only_for_the_identical_drug():
    """Same name and strength isn't enough: the package code must belong to
    the exact drug RxNorm resolved. An extended-release tablet quoted under
    "metformin 500mg" must not price a regular tablet."""
    from fair_refill.costplus import CostPlus
    payload = {"results": [
        {"ndc": "11111111111", "requested_quote": "$3.00", "requested_quote_units": "30", "url": "er"},
        {"ndc": "22222222222", "requested_quote": "$4.50", "requested_quote_units": "30", "url": "ir"},
    ]}
    cp = CostPlus(_FakeHttp(payload))
    assert cp.quote("metformin", "500mg", 30, {"22222222222"}).total == 4.50
    assert cp.quote("metformin", "500mg", 30, {"99999999999"}) is None
