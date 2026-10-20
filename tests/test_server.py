"""
The MCP server, exercised the way Alexa+ would: through an MCP client, over
the protocol, against recorded real prices.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

import pytest
from mcp import Client

from fair_refill.cabinet import Cabinet
from fair_refill.http import replay_client
from fair_refill.server import CARD_URI, build
from fair_refill.service import PriceCheck

FIXTURES = Path(__file__).parent / "fixtures" / "responses.json"

TOOLS = {"check_prescription_price", "check_chosen_medicine", "save_my_medicine", "check_all_my_medicines",
         "remove_my_medicine", "list_my_medicines", "medicare_drug_cost_limits"}


@pytest.fixture
def server(tmp_path):
    return build(PriceCheck(replay_client(FIXTURES), today=date(2026, 10, 6)), Cabinet(tmp_path / "my_medicines.json"))


def call(server, tool, **args):
    async def go():
        async with Client(server, raise_exceptions=True) as client:
            result = await client.call_tool(tool, args)
            assert not result.is_error, result
            data = result.structured_content
            if data is None:                        # some SDK paths only fill text content
                data = json.loads(result.content[0].text)
            return data.get("result", data) if isinstance(data, dict) and set(data) == {"result"} else data
    return asyncio.run(go())


def test_tools_are_listed_with_plain_descriptions_and_the_card(server):
    async def go():
        async with Client(server) as client:
            return (await client.list_tools()).tools
    tools = asyncio.run(go())
    assert {t.name for t in tools} == TOOLS
    for t in tools:
        assert len(t.description) > 40, t.name
        assert "NADAC" not in t.description and "rxcui" not in t.description.lower()
        assert json.dumps(t.meta or {}).find(CARD_URI) != -1, f"{t.name} doesn't point at the card"


def test_card_resource_is_served(server):
    async def go():
        async with Client(server) as client:
            return await client.read_resource(CARD_URI)
    body = asyncio.run(go()).contents[0].text
    script = body.split("<script>")[1]
    # Text from price sources must never be parsed as HTML.
    assert "Fair Refill" in body and "textContent" in script
    assert "innerHTML =" not in script and "insertAdjacentHTML" not in script


def test_price_check_speaks_and_shows(server):
    r = call(server, "check_prescription_price", medicine="atorvastatin 20 mg", you_pay_per_month=40)
    assert r["kind"] == "answer"
    assert "paying about $29 a month more" in r["speech"]
    assert r["card"]["title"] == "atorvastatin 20 mg tablet"
    assert len(r["card"]["details"]) <= 2
    assert r["medicine"]["choice_id"] == "617310"


def test_a_choice_is_priced_exactly_as_offered(server):
    first = call(server, "check_prescription_price", medicine="metformin 500")
    assert first["kind"] == "choose"
    regular = next(c for c in first["choices"] if c["name"] == "metformin 500 mg tablet")
    second = call(server, "check_chosen_medicine", choice_id=regular["choice_id"])
    assert second["kind"] == "answer"
    assert second["speech"].startswith("Pharmacies pay about 44 cents a month for metformin 500 mg tablet")


def test_a_choice_id_that_was_never_offered_is_a_sentence_not_an_error(server):
    r = call(server, "check_chosen_medicine", choice_id="not-a-drug")
    assert r["kind"] == "not_found" and "name again" in r["speech"]


def test_my_medicines_saves_totals_and_forgets(server):
    call(server, "save_my_medicine", choice_id="617310", you_pay_per_month=40)      # atorvastatin 20
    lisinopril = call(server, "check_prescription_price", medicine="lisinopril 10 mg")["medicine"]["choice_id"]
    saved = call(server, "save_my_medicine", choice_id=lisinopril, you_pay_per_month=15)
    assert "You have 2 medicines saved" in saved["speech"]

    summary = call(server, "check_all_my_medicines")
    assert summary["kind"] == "summary"
    total = sum(m["overpaying_by"] or 0 for m in summary["medicines"])
    # Each against Cost Plus delivered: $5.41 and $5.38 for a month, plus $5.25 shipping.
    assert total == pytest.approx((40 - 10.66) + (15 - 10.63), abs=0.05)
    assert "a year" in summary["speech"]

    listed = call(server, "list_my_medicines")
    assert "atorvastatin 20 mg tablet" in listed["speech"]
    assert call(server, "remove_my_medicine", choice_id="617310")["kind"] == "removed"
    assert "atorvastatin" not in call(server, "list_my_medicines")["speech"]


def test_a_list_with_nothing_overpriced_says_so_plainly(server):
    call(server, "save_my_medicine", choice_id="617310", you_pay_per_month=9)       # under the delivered price
    summary = call(server, "check_all_my_medicines")
    assert summary["speech"].startswith("I checked 1 medicine. It doesn't look overpriced")
    assert summary["card"]["details"] == ["1 checked", "Nothing looks overpriced"]


def test_a_shared_server_keeps_no_list_for_someone_it_cannot_tell_apart(tmp_path, monkeypatch):
    """On a server many people reach, one list would hand one person another's
    medicines. Without a key saying whose list is meant, there is none."""
    monkeypatch.setenv("FAIR_REFILL_PUBLIC", "1")
    monkeypatch.setenv("FAIR_REFILL_STATE", str(tmp_path))
    shared = build(PriceCheck(replay_client(FIXTURES), today=date(2026, 10, 6)))
    for tool, args in (("save_my_medicine", {"choice_id": "617310"}), ("list_my_medicines", {}),
                       ("check_all_my_medicines", {}), ("remove_my_medicine", {"choice_id": "617310"})):
        r = call(shared, tool, **args)
        assert r["kind"] == "unavailable" and "can't tell whose" in r["speech"], tool
    assert not any(tmp_path.iterdir())                       # and nothing was written
    # Prices need no list, so they still work.
    assert call(shared, "check_prescription_price", medicine="atorvastatin 20 mg")["kind"] == "answer"


def test_lists_are_kept_apart_by_key(tmp_path):
    from fair_refill.cabinet import Cabinets, Saved
    cabinets = Cabinets(tmp_path, public=True)
    ann, ben = "a" * 32, "b" * 32
    cabinets.of(ann).add(Saved("617310", "atorvastatin 20 mg tablet", 30, 40.0))
    assert [m.name for m in cabinets.of(ann).all()] == ["atorvastatin 20 mg tablet"]
    assert cabinets.of(ben).all() == []
    # A key that is short, or shaped like a path, is no key.
    for bad in ("short", "../../etc/passwd", "a" * 65, "", None):
        assert cabinets.of(bad) is None
    # On someone's own machine there is one list, key or no key.
    assert Cabinets(tmp_path).of(None) is not None


def test_a_which_one_question_is_on_the_screen_too_with_options_to_tap(server):
    r = call(server, "check_prescription_price", medicine="metformin 500")
    assert r["kind"] == "choose"
    assert r["card"]["title"] == "Which one do you take?"
    assert r["card"]["choices"] == r["choices"] and len(r["choices"]) == 2


def test_the_card_leads_with_what_could_be_saved(server):
    r = call(server, "check_prescription_price", medicine="atorvastatin 20 mg", you_pay_per_month=40)
    assert r["card"]["headline"] == "Could save about $29 a month"
    fair = call(server, "check_prescription_price", medicine="atorvastatin 20 mg", you_pay_per_month=12)
    assert "headline" not in fair["card"]                      # nothing to save, so nothing to lead with


def test_empty_list_says_what_to_do(server):
    r = call(server, "check_all_my_medicines")
    assert r["kind"] == "empty" and "remember it" in r["speech"]


def test_medicare_limits(server):
    r = call(server, "medicare_drug_cost_limits")
    assert "$2,100" in r["speech"] and "$35" in r["speech"]


def test_a_misheard_quantity_falls_back_to_a_month(server):
    r = call(server, "check_prescription_price", medicine="atorvastatin 20 mg", monthly_quantity=30000)
    assert "84 cents a month" in r["speech"]


def test_lists_are_said_the_way_people_say_them():
    from fair_refill.server import _spoken_list
    assert _spoken_list(["a"]) == "a"
    assert _spoken_list(["a", "b"]) == "a and b"
    assert _spoken_list(["a", "b", "c"]) == "a, b, and c"
