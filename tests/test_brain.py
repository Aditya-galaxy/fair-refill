"""The simulator's router: what people say, to which tool."""

from __future__ import annotations

import pytest

from fair_refill.brain import State, medicine_said, money_said, quantity_said, route

METFORMIN = [{"choice_id": "861004", "name": "metformin 500 mg extended-release tablet"},
             {"choice_id": "861007", "name": "metformin 500 mg tablet"}]
ATORVA = [{"choice_id": "a10", "name": "atorvastatin 10 mg tablet"},
          {"choice_id": "a20", "name": "atorvastatin 20 mg tablet"},
          {"choice_id": "a40", "name": "atorvastatin 40 mg tablet"}]


@pytest.mark.parametrize("said, dollars", [
    ("I pay $40 a month", 40.0), ("it's 40 dollars", 40.0), ("forty dollars a month", 40.0),
    ("I pay forty five dollars", 45.0), ("$12.50", 12.5), ("atorvastatin 20 mg", None),
])
def test_money_said(said, dollars):
    assert money_said(said) == dollars


@pytest.mark.parametrize("said, n", [("twice a day", 60), ("once a day", 30), ("90 tablets a month", 90),
                                     ("sixty tablets a month", 60), ("atorvastatin", None)])
def test_quantity_said(said, n):
    assert quantity_said(said) == n


@pytest.mark.parametrize("said, medicine", [
    ("What will Ozempic cost me next year?", "Ozempic"),
    ("what's Medicare's negotiated price for Tradjenta", "Tradjenta"),
    ("is my Linzess 145 mcg going to get cheaper in January", "Linzess 145 mcg"),
    ("Alexa, ask Fair Refill if I'm overpaying for my atorvastatin 20 mg. I pay $40 a month.", "atorvastatin 20 mg"),
    ("How much should Lipitor 20 cost?", "Lipitor 20"),
    ("am I paying too much for lisinopril 10 milligrams", "lisinopril 10 milligrams"),
    ("check my metformin", "metformin"),
])
def test_medicine_said(said, medicine):
    assert medicine_said(said) == medicine


def test_price_check_with_what_they_pay():
    tool, args = route("Am I overpaying for my atorvastatin 20 mg? I pay forty dollars a month", State())
    assert tool == "check_prescription_price"
    assert args == {"medicine": "atorvastatin 20 mg", "monthly_quantity": 30, "you_pay_per_month": 40.0}


def test_twice_a_day_is_sixty_a_month():
    _, args = route("metformin 500 mg twice a day", State())
    assert args["monthly_quantity"] == 60


@pytest.mark.parametrize("said, picked", [
    ("the regular one", "861007"), ("regular tablet", "861007"), ("the plain one", "861007"),
    ("extended release", "861004"), ("the first one", "861004"), ("the second", "861007"),
])
def test_picking_a_choice(said, picked):
    tool, args = route(said, State(choices=METFORMIN))
    assert tool == "check_chosen_medicine" and args["choice_id"] == picked


def test_picking_by_strength():
    tool, args = route("the 20 milligram", State(choices=ATORVA))
    assert tool == "check_chosen_medicine" and args["choice_id"] == "a20"


def test_an_ambiguous_pick_is_not_guessed():
    tool, _ = route("the tablet", State(choices=METFORMIN))
    assert tool != "check_chosen_medicine"


def test_what_they_pay_carries_into_the_choice():
    _, args = route("the regular one", State(choices=METFORMIN, you_pay=25.0))
    assert args["you_pay_per_month"] == 25.0


@pytest.mark.parametrize("said, tool", [
    ("check all my medicines", "check_all_my_medicines"),
    ("am I overpaying for any of my prescriptions", "check_all_my_medicines"),
    ("what's on my list", "list_my_medicines"),
    ("what's the Medicare limit on drug costs", "medicare_drug_cost_limits"),
    ("is there a cap on what Medicare makes me pay", "medicare_drug_cost_limits"),
])
def test_other_intents(said, tool):
    assert route(said, State())[0] == tool


def test_remember_needs_something_to_remember():
    assert route("remember this", State())[0] == "say"
    tool, args = route("remember this", State(medicine={"choice_id": "a20", "name": "x"}, you_pay=40.0))
    assert tool == "save_my_medicine" and args["choice_id"] == "a20" and args["you_pay_per_month"] == 40.0


def test_nothing_named_asks_which_medicine():
    tool, args = route("am I paying too much", State())
    assert tool == "say" and "Which medicine" in args["speech"]
