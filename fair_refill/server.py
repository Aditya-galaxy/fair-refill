"""
Fair Refill as an MCP server: the add-on Alexa+ would call.

    python -m fair_refill.server            # Streamable HTTP on http://127.0.0.1:8765/mcp

Written to Alexa+'s functional requirements for MCP add-ons:

  * one tool per thing a person wants, each described in plain words with the
    phrasings people use;
  * every result carries a short spoken answer, so a screenless device has
    everything it needs, plus a card for devices with a screen (an MCP App,
    `ui://fair-refill/card.html`);
  * choices come back with stable IDs, so "the regular tablet" can be priced
    exactly as offered;
  * no error codes or jargon reach the person: every failure is a sentence
    with a next step.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.apps import Apps
from mcp.server.mcpserver import Context, MCPServer

from . import medicare, prewarm
from .cabinet import LIST_HEADER, Cabinet, Cabinets, Saved
from .compare import CASH_CAVEAT, Finding, money
from .service import PriceCheck, Result

ROOT = Path(__file__).resolve().parent.parent
CARD_URI = "ui://fair-refill/card.html"
CARD_HTML = (Path(__file__).parent / "card.html").read_text(encoding="utf-8")
# The Agent Skill that goes with the add-on: how to hold the conversation
# around these tools. Served by the add-on too, so a client that connects can
# read how it's meant to be used without having the repository.
SKILL_URI = "skill://fair-refill/SKILL.md"
SKILL_PATH = ROOT / "skills" / "fair-refill" / "SKILL.md"

NO_LIST = {"kind": "unavailable",
           "speech": "I can't keep a list of medicines here, because I can't tell whose it would be. "
                     "I can still check any medicine's price."}

INSTRUCTIONS = """Fair Refill checks whether someone is paying more than they need to for a prescription.
It compares only the identical medicine, never a substitute, and every answer ends with what to ask
the pharmacist, doctor or plan. Read the `speech` field to the person as written; it is already
short and plain. When the result is a choice, ask the question in `speech` and call
check_chosen_medicine with the `choice_id` they pick."""


def _card(f: Finding | None) -> dict[str, Any] | None:
    if f is None:
        return None
    return {"title": f.title, "details": list(f.details), "action": f.action, "sources": list(f.sources)}


def _payload(r: Result) -> dict[str, Any]:
    return {
        "kind": r.kind,
        "speech": r.speech,
        "card": _card(r.finding),
        "choices": [{"choice_id": d.rxcui, "name": d.spoken} for d in r.choices] if r.kind == "choose" else [],
        "medicine": ({"choice_id": r.choices[0].rxcui, "name": r.choices[0].spoken}
                     if r.kind == "answer" and r.choices else None),
    }


def build(check: PriceCheck | None = None, cabinet: Cabinet | None = None) -> MCPServer:
    state = Path(os.environ.get("FAIR_REFILL_STATE", ROOT / "state"))
    check = check or PriceCheck(cache_dir=prewarm.cache_dir())
    cabinets = Cabinets(state, public=os.environ.get("FAIR_REFILL_PUBLIC", "0") == "1", own=cabinet)

    def my_list(ctx: Context) -> Cabinet | None:
        return cabinets.of((ctx.headers or {}).get(LIST_HEADER))

    apps = Apps()
    apps.add_html_resource(CARD_URI, CARD_HTML, title="Fair Refill card",
                           description="A glanceable price card, sized to be read across a room.")

    @apps.tool(resource_uri=CARD_URI, name="check_prescription_price",
               description=(
                   "Check whether someone is overpaying for a prescription. Use when they ask 'am I paying "
                   "too much for my atorvastatin', 'how much should Lipitor cost', 'is there a cheaper way "
                   "to get my metformin', 'what will Ozempic cost next year', 'what's Medicare's price for "
                   "Eliquis', or name a medicine and what they pay. `medicine` is the name as "
                   "said, with the strength if given ('lisinopril 10 mg', 'Lipitor 20'); misspellings are "
                   "corrected. `monthly_quantity` is tablets or capsules a month (default 30). "
                   "`you_pay_per_month` is what they pay now, in dollars, if they said."))
    def check_prescription_price(medicine: str, monthly_quantity: int = 30,
                                 you_pay_per_month: float | None = None) -> dict[str, Any]:
        return _payload(check.ask(medicine, _quantity(monthly_quantity), you_pay_per_month))

    @apps.tool(resource_uri=CARD_URI, name="check_chosen_medicine",
               description=(
                   "Price the exact medicine someone picked after check_prescription_price asked which one "
                   "they take ('the regular tablet', 'the 20 milligram'). `choice_id` must be one of the "
                   "choice_id values that tool returned."))
    def check_chosen_medicine(choice_id: str, monthly_quantity: int = 30,
                              you_pay_per_month: float | None = None) -> dict[str, Any]:
        drug = check.rx.drug(choice_id)
        if drug is None:
            return _payload(Result("not_found", "I lost track of which medicine that was. "
                                                "Tell me its name again, with the strength."))
        return _payload(check.check(drug, _quantity(monthly_quantity), you_pay_per_month))

    @apps.tool(resource_uri=CARD_URI, name="save_my_medicine",
               description=(
                   "Remember a medicine on the person's list, so 'check all my medicines' covers it. Use "
                   "when they say 'remember this', 'add it to my list', 'save my lisinopril'. `choice_id` "
                   "comes from a previous price check."))
    def save_my_medicine(choice_id: str, ctx: Context, monthly_quantity: int = 30,
                         you_pay_per_month: float | None = None) -> dict[str, Any]:
        cabinet = my_list(ctx)
        if cabinet is None:
            return NO_LIST
        drug = check.rx.drug(choice_id)
        if drug is None:
            return {"kind": "not_found", "speech": "I couldn't tell which medicine to save. Check its price "
                                                   "first, then ask me to remember it."}
        cabinet.add(Saved(drug.rxcui, drug.spoken, _quantity(monthly_quantity), you_pay_per_month))
        count = len(cabinet.all())
        return {"kind": "saved", "speech": f"I've added {drug.spoken} to your list. "
                                           f"You have {count} {'medicine' if count == 1 else 'medicines'} saved."}

    @apps.tool(resource_uri=CARD_URI, name="check_all_my_medicines",
               description=(
                   "Check every saved medicine at once and total what the person could save. Use for 'check "
                   "all my medicines', 'am I overpaying for any of my prescriptions', 'go through my list'."))
    def check_all_my_medicines(ctx: Context) -> dict[str, Any]:
        cabinet = my_list(ctx)
        if cabinet is None:
            return NO_LIST
        saved = cabinet.all()
        if not saved:
            return {"kind": "empty", "speech": "Your list is empty. Check a medicine's price, then ask me to "
                                               "remember it."}
        rows, total = [], 0.0
        for item in saved:
            drug = check.rx.drug(item.choice_id)
            if drug is None:
                continue
            r = check.check(drug, item.monthly_quantity, item.you_pay_per_month)
            over = r.finding.overpaying_by if r.finding else None
            rows.append({"name": item.name, "overpaying_by": over, "speech": r.speech})
            # Each medicine is counted with its own shipping, though one
            # order would carry several: the total errs on the low side.
            total += over or 0.0
        flagged = [r for r in rows if r["overpaying_by"]]
        if not flagged:
            checked = "1 medicine. It doesn't look" if len(rows) == 1 else f"{len(rows)} medicines. None looks"
            speech = (f"I checked {checked} overpriced for what you told me you pay. "
                      "For any without a price, ask your pharmacist for the cash price.")
        else:
            names = _spoken_list([r["name"] for r in flagged])
            speech = (f"You may be able to save about {money(total)} a month, or {money(total * 12)} a year, "
                      f"on {names}. {CASH_CAVEAT} Ask your pharmacist or plan which way costs you less "
                      "over the year.")
        return {"kind": "summary", "speech": speech, "medicines": rows,
                "card": {"title": "Your medicines",
                         "details": [f"{len(rows)} checked",
                                     f"Could save: {money(total)}/mo" if flagged else "Nothing looks overpriced"],
                         "action": "Ask about cash prices" if flagged else "No change needed", "sources": []}}

    @apps.tool(resource_uri=CARD_URI, name="remove_my_medicine",
               description="Take a medicine off the person's saved list ('remove my lisinopril', "
                           "'I don't take that any more'). `choice_id` from the saved list.")
    def remove_my_medicine(choice_id: str, ctx: Context) -> dict[str, Any]:
        cabinet = my_list(ctx)
        if cabinet is None:
            return NO_LIST
        gone = cabinet.remove(choice_id)
        if gone is None:
            return {"kind": "not_found", "speech": "That medicine wasn't on your list."}
        return {"kind": "removed", "speech": f"I've removed {gone.name} from your list."}

    @apps.tool(resource_uri=CARD_URI, name="list_my_medicines",
               description="Say which medicines are on the person's saved list ('what's on my list').")
    def list_my_medicines(ctx: Context) -> dict[str, Any]:
        cabinet = my_list(ctx)
        if cabinet is None:
            return NO_LIST
        saved = cabinet.all()
        if not saved:
            return {"kind": "empty", "speech": "Your list is empty."}
        listed = _spoken_list([s.name for s in saved])
        return {"kind": "list", "speech": f"Your list has {listed}.",
                "medicines": [{"choice_id": s.choice_id, "name": s.name} for s in saved]}

    @apps.tool(resource_uri=CARD_URI, name="medicare_drug_cost_limits",
               description=(
                   "Explain this year's Medicare limits on prescription costs. Use for 'is there a limit on "
                   "what Medicare makes me pay', 'my drugs are too expensive this year', 'Medicare drug cap'."))
    def medicare_drug_cost_limits() -> dict[str, Any]:
        speech = (f"This year, if you have Medicare drug coverage, what you pay for covered prescriptions stops "
                  f"at {money(medicare.PART_D_CAP)}. You can also ask your plan to spread that over the year "
                  f"in monthly payments, and insulin costs no more than ${medicare.INSULIN_MONTHLY_CAP} a month. "
                  "Your plan can tell you how much you've paid so far.")
        return {"kind": "answer", "speech": speech,
                "card": {"title": f"Medicare drug costs, {medicare.YEAR}",
                         "details": [f"Yearly cap: {money(medicare.PART_D_CAP)}",
                                     f"Insulin: ${medicare.INSULIN_MONTHLY_CAP}/mo max"],
                         "action": "Ask your plan", "sources": [medicare.PART_D_CAP_SOURCE]}}

    server = MCPServer("Fair Refill", title="Fair Refill", instructions=INSTRUCTIONS, version="0.1.0",
                       extensions=[apps])

    if SKILL_PATH.exists():
        @server.resource(SKILL_URI, name="fair-refill-skill", title="Fair Refill Agent Skill",
                         description="How to use these tools in a conversation: what to ask, what to say, "
                                     "and the rules an answer must keep.", mime_type="text/markdown")
        def skill() -> str:
            return SKILL_PATH.read_text(encoding="utf-8")

    return server


def _spoken_list(names: list[str]) -> str:
    """"a", "a and b", "a, b, and c" — the way a list is said."""
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _quantity(n: int) -> int:
    """A month of a medicine is between 1 and 360 units; anything else is a mishearing."""
    return n if isinstance(n, int) and 1 <= n <= 360 else 30


def main() -> None:
    import uvicorn

    host = os.environ.get("FAIR_REFILL_HOST", "127.0.0.1")
    port = int(os.environ.get("FAIR_REFILL_PORT", "8765"))
    # FAIR_REFILL_STATELESS=1 keeps nothing between requests, so any copy of
    # the server can answer any of them. Hosts that run several copies, or
    # that manage sessions themselves (Bedrock AgentCore Runtime), need it.
    app = build().streamable_http_app(host=host, stateless_http=os.environ.get("FAIR_REFILL_STATELESS", "0") == "1")
    prewarm.in_background()
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
