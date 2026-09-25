"""
The answer: is this person paying more than they need to for this medicine?

A pure function over prices that have already been fetched. It decides what
Alexa says and what the card shows, and nothing else: no network, no state,
so every sentence can be tested against known prices.

Rules it keeps, because each one is where a well-meant answer could hurt
someone:

  * Only the identical drug is ever priced (the caller guarantees it via
    RxNorm; this module never suggests a different medicine, strength or
    dose, and never suggests skipping or stopping one).
  * A brand-to-generic comparison is framed as a question for the pharmacist
    or doctor, never as an instruction.
  * Every figure says what it is: what pharmacies pay, a cash price you can
    buy at, or Medicare's negotiated price — and how current it is.
  * It says what it can't do. Inhalers, liquids and creams are priced per
    gram or millilitre, which needs a package size this doesn't have yet;
    for those it says so instead of guessing.
  * No jargon in anything spoken: "what pharmacies pay", never "NADAC".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import medicare, rxpass
from .costplus import Quote
from .nadac import NadacPrice
from .rxnorm import Drug

# Below these, a gap isn't worth telling someone to act on: a few dollars a
# month, or a small share of what they pay.
_WORTH_IT_DOLLARS = 3.0
_WORTH_IT_SHARE = 0.2


@dataclass(frozen=True)
class Option:
    label: str
    monthly: float | None
    note: str = ""


@dataclass(frozen=True)
class Finding:
    medicine: str
    speech: str
    title: str
    details: tuple[str, ...]          # at most two, for a card read across a room
    action: str
    options: tuple[Option, ...] = ()
    overpaying_by: float | None = None
    sources: tuple[str, ...] = ()
    comparable: bool = True
    notes: tuple[str, ...] = field(default=())


def money(x: float) -> str:
    """How an amount is said: "84 cents", "$5", "$5.41", "$231"."""
    if x < 1:
        return f"{max(1, round(x * 100))} cents"
    if x < 10:
        return f"${x:.0f}" if abs(x - round(x)) < 0.005 else f"${x:.2f}"
    return f"${x:,.0f}"


def _where_to_buy(cash: Option | None, sub: Option | None) -> str:
    """One sentence, both places, each with the condition that matters."""
    parts = []
    if cash:
        parts.append(f"Cost Plus Drugs sells it for {money(cash.monthly)} a month plus shipping")
    if sub:
        parts.append(f"Amazon RxPass covers it for {money(sub.monthly)} a month with Prime, outside insurance")
    return (", and ".join(parts) + ".") if parts else ""


def comparable_form(form: str) -> bool:
    """Tablets and capsules are priced per unit, so a month is units x price.
    Everything else is priced per gram or millilitre and needs a package size."""
    return "tablet" in form or "capsule" in form


def cannot_compare(drug: Drug) -> Finding:
    return Finding(
        medicine=drug.spoken, comparable=False,
        speech=(f"I can compare prices for tablets and capsules, but not yet for {drug.form.split()[-1]}s. "
                "Ask your pharmacist for the cash price. They're allowed to tell you "
                "when paying cash costs less than your insurance."),
        title=drug.spoken, details=("Price check covers tablets and capsules", "Ask for the cash price"),
        action="Ask your pharmacist", sources=(medicare.GAG_CLAUSE_BAN_SOURCE,))


def _card_money(x: float) -> str:
    return f"${x:,.2f}" if x < 100 else f"${x:,.0f}"


def assess(*, asked: Drug, generic: Drug, quantity: int, asked_cost: NadacPrice | None,
           generic_cost: NadacPrice | None, cash: Quote | None, you_pay: float | None = None) -> Finding:
    """`asked` is what the person named (brand or generic); `generic` is the
    same clinical drug without a brand. `quantity` is units a month."""
    name = asked.spoken
    is_brand = asked.tty == "SBD"
    negotiated = medicare.negotiated_for(asked.brand)
    sources = []

    unit = (asked_cost or generic_cost).unit if (asked_cost or generic_cost) else "EA"
    if (unit != "EA" or not comparable_form(asked.form)) and not negotiated:
        return cannot_compare(asked)

    options: list[Option] = []
    benchmark = generic_cost.per_unit * quantity if generic_cost and generic_cost.unit == "EA" else None
    if generic_cost:
        sources.append(f"CMS NADAC, {generic_cost.as_of}")
    cash_month = cash.total * quantity / cash.quantity if cash else None
    if cash_month is not None:
        options.append(Option("Cost Plus Drugs", cash_month, "plus shipping"))
        sources.append("Cost Plus Drugs public prices")
    if rxpass.may_cover(generic.ingredients, generic.form):
        options.append(Option("Amazon RxPass", float(rxpass.PRICE_PER_MONTH),
                              "if your strength is covered; " + "; ".join(rxpass.CAVEATS)))
        sources.append(f"Amazon RxPass list, {rxpass.CHECKED}")

    cash_opt = next((o for o in options if o.label == "Cost Plus Drugs"), None)
    sub_opt = next((o for o in options if o.label == "Amazon RxPass"), None)
    # The reference price is one anyone can buy at. RxPass needs Prime and
    # bypasses insurance, so it's mentioned, never used to tell someone they
    # are overpaying.
    cheapest = cash_opt or sub_opt
    sentences: list[str] = []
    details: list[str] = []

    # ── a brand with no generic on sale: Medicare's negotiated price and cap ──
    if is_brand and negotiated and not (generic_cost and generic_cost is not asked_cost) and not cash:
        sentences.append(f"Medicare's negotiated price for {asked.brand} is {money(negotiated.price_30_day)} "
                         f"for a 30-day supply this year, down from {money(negotiated.list_price_30_day_2023)}.")
        sentences.append(f"If you have Medicare drug coverage, what you pay for covered drugs this year stops at "
                         f"{money(medicare.PART_D_CAP)}, and you can spread it over monthly payments.")
        sentences.append("Ask your plan how much of the new price you pay.")
        return Finding(
            medicine=name, speech=" ".join(sentences), title=name,
            details=(f"Medicare price: {_card_money(negotiated.price_30_day)} / 30 days",
                     f"Yearly cap: {_card_money(medicare.PART_D_CAP)}"),
            action="Ask your plan", options=tuple(options),
            sources=(f"CMS negotiated prices {medicare.YEAR}", medicare.PART_D_CAP_SOURCE))

    # ── a brand with a generic ───────────────────────────────────────────────
    if is_brand and asked_cost and benchmark is not None:
        brand_month = asked_cost.per_unit * quantity
        sentences.append(f"Pharmacies pay about {money(brand_month)} a month for {name}, and about "
                         f"{money(benchmark)} for the generic, {generic.spoken}.")
        details.append(f"Brand: {_card_money(brand_month)}/mo · generic: {_card_money(benchmark)}/mo")
        if cheapest:
            sentences.append("For the generic: " + _where_to_buy(cash_opt, sub_opt))
            details.append(f"{cheapest.label}: {_card_money(cheapest.monthly)}/mo")
        sentences.append("Ask your pharmacist or doctor whether the generic is right for you.")
        if negotiated:
            sentences.append(f"With Medicare, the negotiated price for {asked.brand} is "
                             f"{money(negotiated.price_30_day)} a month this year.")
        return Finding(medicine=name, speech=" ".join(sentences), title=name, details=tuple(details[:2]),
                       action="Ask about the generic", options=tuple(options), sources=tuple(sources))

    # ── a generic, or a brand we can only price as itself ────────────────────
    overpaying = None
    if you_pay is not None and cheapest and you_pay - cheapest.monthly >= max(_WORTH_IT_DOLLARS,
                                                                           _WORTH_IT_SHARE * cheapest.monthly):
        overpaying = you_pay - cheapest.monthly
        sentences.append(f"You may be paying about {money(overpaying)} a month more than you need to "
                         f"for {name}.")
        sentences.append(_where_to_buy(cash_opt, sub_opt))
        sentences.append("Ask your pharmacist whether paying cash would cost less than your insurance. "
                         "They're allowed to tell you.")
        details = [f"You pay: {_card_money(you_pay)}/mo",
                   f"{cheapest.label}: {_card_money(cheapest.monthly)}/mo"]
        action = "Ask about the cash price"
    elif you_pay is not None and cheapest:
        sentences.append(f"{money(you_pay)} a month for {name} is a fair price.")
        if benchmark is not None:
            sentences.append(f"Pharmacies pay about {money(benchmark)} a month for it.")
        details = [f"You pay: {_card_money(you_pay)}/mo", f"Lowest found: {_card_money(cheapest.monthly)}/mo"]
        action = "No change needed"
    else:
        if benchmark is not None:
            sentences.append(f"Pharmacies pay about {money(benchmark)} a month for {name}.")
            details.append(f"Pharmacies pay: {_card_money(benchmark)}/mo")
        if cheapest:
            sentences.append(_where_to_buy(cash_opt, sub_opt))
            sentences.append("If you pay more than that, ask your pharmacist about the cash price.")
            details.append(f"{cheapest.label}: {_card_money(cheapest.monthly)}/mo")
        elif benchmark is not None:
            sentences.append("Ask your pharmacist for the cash price. They're allowed to tell you when "
                             "paying cash costs less than your insurance.")
        else:
            sentences.append(f"I couldn't find a current price for {name}. Ask your pharmacist for the cash "
                             f"price.")
        action = "Ask about the cash price"

    return Finding(medicine=name, speech=" ".join(sentences), title=name, details=tuple(details[:2]),
                   action=action, options=tuple(options), overpaying_by=overpaying, sources=tuple(sources))
