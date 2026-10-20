"""
What a month of each common generic costs, at the door, from the add-on's own sources.

    python tools/measure_savings.py          # writes docs/savings.md and docs/savings.json

For every tablet and capsule strength of the generic names the server keeps
warm (prewarm.MEDICINES), this asks the same sources the add-on asks, the same
way: what pharmacies pay (CMS NADAC), Cost Plus Drugs for a month and for three
months in one fill (with its $5.25 shipping added), and whether Amazon RxPass's
list may cover it. It reads through the add-on's cache, so a run right after a
pre-warm round makes few new requests.

It measures prices, not what anyone pays: copays differ by plan, and no public
source lists them. So the summary says what a month costs, and leaves "you're
overpaying" to the comparison a person makes with their own copay.
"""

from __future__ import annotations

import json
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fair_refill import prewarm, rxpass  # noqa: E402
from fair_refill.compare import comparable_form  # noqa: E402
from fair_refill.costplus import LONG_SUPPLY_MONTHS  # noqa: E402
from fair_refill.http import SourceUnavailable  # noqa: E402
from fair_refill.service import PriceCheck  # noqa: E402

MONTH = 30                       # tablets or capsules a month: once a day
OUT = ROOT / "docs"


def measure(check: PriceCheck, name: str) -> list[dict]:
    rows = []
    # Each row keeps the name it was found under, so the summary can say how
    # many of the generics Cost Plus sells at all, not only how many strengths.
    for drug in check.rx.search(name)[0]:
        if not comparable_form(drug.form):
            continue
        ndcs = check.rx.ndcs(drug.rxcui)
        cost = check.nadac.price(ndcs)
        month = check.costplus.quote(drug.ingredient, drug.strength_token, MONTH, set(ndcs))
        long = check.costplus.quote(drug.ingredient, drug.strength_token, MONTH * LONG_SUPPLY_MONTHS, set(ndcs))
        rows.append({
            "generic": name,
            "medicine": drug.spoken,
            "pharmacies_pay_month": round(cost.per_unit * MONTH, 2) if cost and cost.unit == "EA" else None,
            "nadac_as_of": cost.as_of if cost else None,
            "cost_plus_month_delivered": round(month.delivered(MONTH), 2) if month else None,
            "cost_plus_three_months_per_month": (round(long.delivered(MONTH * LONG_SUPPLY_MONTHS)
                                                       / LONG_SUPPLY_MONTHS, 2) if long else None),
            "rxpass_may_cover": rxpass.may_cover(drug.ingredients, drug.form),
        })
    return rows


def share(n: int, of: int) -> str:
    return f"{n} of {of} ({round(100 * n / of)}%)" if of else "none"


def main() -> int:
    check = PriceCheck(cache_dir=prewarm.cache_dir())
    names = [m for m in prewarm.MEDICINES if m.islower()]            # generics; brands are Medicare's story
    rows: list[dict] = []
    missed = []
    for name in names:
        try:
            rows += measure(check, name)
        except SourceUnavailable:
            missed.append(name)
    today = date.today().isoformat()
    OUT.mkdir(exist_ok=True)
    (OUT / "savings.json").write_text(json.dumps({"measured": today, "tablets_a_month": MONTH, "rows": rows},
                                                 indent=1), encoding="utf-8")

    carried = [r for r in rows if r["cost_plus_month_delivered"] is not None]
    month = sorted(r["cost_plus_month_delivered"] for r in carried)
    three = sorted(r["cost_plus_three_months_per_month"] for r in carried
                   if r["cost_plus_three_months_per_month"] is not None)
    cheap = [r for r in carried if r["cost_plus_month_delivered"] < 15]
    cheap_three = [x for x in three if x < 5]
    rxp = [r for r in rows if r["rxpass_may_cover"]]
    measured = sorted({r["generic"] for r in rows})
    sold = sorted({r["generic"] for r in carried})
    summary = [
        f"- **{len(measured)} common generics**, every tablet and capsule strength RxNorm lists: "
        f"{len(rows)} in all, {MONTH} a month.",
        f"- **Cost Plus Drugs sells {share(len(sold), len(measured))} of the generics**, and "
        f"{share(len(carried), len(rows))} of the strengths. RxNorm lists every approved product, including "
        "rarely used ones, so the strengths it doesn't sell are mostly the unusual ones.",
        f"- Where it does, a month delivered costs **${statistics.median(month):.2f} at the median**, and "
        f"**{share(len(cheap), len(carried))} cost under $15**. The dearest are unusual products, and this "
        f"prices everything at {MONTH} a month, so a once-a-week capsule is overstated; the table shows each.",
        f"- Three months in one fill comes to **${statistics.median(three):.2f} a month at the median**; "
        f"{share(len(cheap_three), len(three))} come under $5 a month.",
        f"- Amazon RxPass's list may cover **{share(len(rxp), len(rows))}** ($5 a month with Prime, outside "
        "insurance; Amazon doesn't list strengths).",
    ]
    unsold = [g for g in measured if g not in sold]
    if unsold:
        summary.append(f"- Not sold by Cost Plus in any strength: {', '.join(unsold)}.")
    if missed:
        summary.append(f"- No answer from a source for: {', '.join(missed)}.")
    table = ["| Medicine | Pharmacies pay / month | Cost Plus, a month delivered | Cost Plus, 3 months, per month "
             "| RxPass may cover |", "|---|---|---|---|---|"]

    def cell(x: float | None) -> str:
        return "—" if x is None else f"${x:,.2f}"

    for r in rows:
        table.append(f"| {r['medicine']} | {cell(r['pharmacies_pay_month'])} | {cell(r['cost_plus_month_delivered'])} "
                     f"| {cell(r['cost_plus_three_months_per_month'])} | {'yes' if r['rxpass_may_cover'] else ''} |")
    (OUT / "savings.md").write_text(
        f"# What a month of a common generic costs\n\n"
        f"Measured {today} by `tools/measure_savings.py`, from the sources Fair Refill answers from: CMS NADAC "
        f"(what pharmacies pay), the Cost Plus Drugs public API (with its $5.25 shipping an order added) and "
        f"Amazon's RxPass list. Every tablet and capsule strength of the generics the add-on keeps ready.\n\n"
        + "\n".join(summary) +
        "\n\nThese are prices, not what anyone pays: copays vary by plan, and no public source lists them. "
        "Someone whose copay is above the delivered price for their medicine is who the add-on is for.\n\n"
        + "\n".join(table) + "\n", encoding="utf-8")
    print("\n".join(summary))
    print(f"\n  docs/savings.md and docs/savings.json, {len(rows)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
