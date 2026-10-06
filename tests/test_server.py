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
    assert "paying about $35 a month more" in r["speech"]
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
    assert total == pytest.approx((40 - 5.41) + 9.62, abs=0.05)
    assert "a year" in summary["speech"]

    listed = call(server, "list_my_medicines")
    assert "atorvastatin 20 mg tablet" in listed["speech"]
    assert call(server, "remove_my_medicine", choice_id="617310")["kind"] == "removed"
    assert "atorvastatin" not in call(server, "list_my_medicines")["speech"]


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
