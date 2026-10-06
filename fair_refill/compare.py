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
  * A cash price is never offered without its catch: money paid outside
    insurance usually doesn't count toward a deductible or Medicare's yearly
    limit, so for someone on several medicines the cheaper refill can be the
    dearer year.
  * No jargon in anything spoken: "what pharmacies pay", never "NADAC".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from . import medicare, rxpass
from .costplus import Quote
from .nadac import NadacPrice
from .rxnorm import Drug

# Below these, a gap isn't worth telling someone to act on: a few dollars a
# month, or a small share of what they pay.
_WORTH_IT_DOLLARS = 3.0
_WORTH_IT_SHARE = 0.2

# Said whenever a cash price is. "Usually", because a few plans accept a claim
# for a cash purchase; the pharmacist or plan knows which.
CASH_CAVEAT = "Cash prices usually don't count toward your deductible or Medicare's yearly limit."


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


def _coming(n: medicare.NegotiatedPrice) -> str:
    # "About", and "typical": CMS gives one figure for every strength and form
    # of a drug, and a package of one strength can cost more or less than it.
    return (f"From January {n.starts.year}, Medicare's negotiated price for {{brand}} is about "
            f"{money(n.price_30_day)} for a typical 30-day supply, down from a list price of "
            f"{money(n.list_price_30_day)}.")


def medicare_price(drug: Drug, today: date | None = None, now_costs: float | None = None,
                   whole_brand: bool = False) -> Finding | None:
    """For a brand Medicare has negotiated a price for: that price, in force
    or coming, and what to ask the plan. It needs no pharmacy price, so it
    answers for injections and inhalers too. `now_costs` is what pharmacies
    pay for a month today, when that's known. `whole_brand` answers for the
    brand rather than one strength of it: CMS gives one figure for all."""
    today = today or date.today()
    if whole_brand and drug.brand:
        drug = Drug(drug.rxcui, f"{drug.brand} [{drug.brand}]", drug.tty)
    current, coming = medicare.negotiated_for(drug.brand, today), medicare.upcoming_for(drug.brand, today)
    if current:
        speech = [f"Medicare's negotiated price for {drug.brand} is {money(current.price_30_day)} "
                  f"for a 30-day supply this year, down from {money(current.list_price_30_day)}.",
                  f"If you have Medicare drug coverage, what you pay for covered drugs this year stops at "
                  f"{money(medicare.PART_D_CAP)}, and you can spread it over monthly payments.",
                  "Ask your plan how much of the new price you pay."]
        return Finding(medicine=drug.spoken, speech=" ".join(speech), title=drug.spoken,
                       details=(f"Medicare price: {_card_money(current.price_30_day)} / 30 days",
                                f"Yearly cap: {_card_money(medicare.PART_D_CAP)}"),
                       action="Ask your plan",
                       sources=(f"CMS negotiated prices {current.starts.year}", medicare.PART_D_CAP_SOURCE))
    if coming:
        speech = []
        if now_costs is not None:
            speech.append(f"Pharmacies pay about {money(now_costs)} a month for {drug.spoken} now.")
        speech.append(_coming(coming).format(brand=drug.brand))
        if medicare.open_enrollment(today):
            speech.append("Medicare open enrollment runs until December 7, so now is the time to check how "
                          "each plan covers it.")
        speech.append("Ask your plan what you'll pay from January.")
        return Finding(medicine=drug.spoken, speech=" ".join(speech), title=drug.spoken,
                       details=(f"From Jan {coming.starts.year}: about {_card_money(coming.price_30_day)} / 30 days",
                                f"List price: {_card_money(coming.list_price_30_day)}"),
                       action="Ask your plan",
                       sources=(f"CMS negotiated prices {coming.starts.year}",))
    return None


def assess(*, asked: Drug, generic: Drug, quantity: int, asked_cost: NadacPrice | None,
           generic_cost: NadacPrice | None, cash: Quote | None, you_pay: float | None = None,
           today: date | None = None) -> Finding:
    """`asked` is what the person named (brand or generic); `generic` is the
    same clinical drug without a brand. `quantity` is units a month."""
    name = asked.spoken
    is_brand = asked.tty == "SBD"
    today = today or date.today()
    negotiated = medicare.negotiated_for(asked.brand, today)
    coming = medicare.upcoming_for(asked.brand, today)
    sources = []

    unit = (asked_cost or generic_cost).unit if (asked_cost or generic_cost) else "EA"
    priced_per_unit = unit == "EA" and comparable_form(asked.form)
    if not priced_per_unit and not (negotiated or coming):
        return cannot_compare(asked)

    options: list[Option] = []
    benchmark = generic_cost.per_unit * quantity if generic_cost and generic_cost.unit == "EA" else None
    if generic_cost:
        sources.append(f"CMS NADAC, {generic_cost.as_of}")
    cash_month = cash.total * quantity / cash.quantity if cash else None
    if cash_month is not None:
        options.append(Option("Cost Plus Drugs", cash_month, "plus shipping; outside insurance"))
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

    # ── a brand with no generic on sale: Medicare's negotiated price ─────────
    if is_brand and (negotiated or coming) and not (generic_cost and generic_cost is not asked_cost) and not cash:
        now_costs = asked_cost.per_unit * quantity if asked_cost and priced_per_unit else None
        found = medicare_price(asked, today, now_costs)
        return Finding(medicine=found.medicine, speech=found.speech, title=found.title, details=found.details,
                       action=found.action, options=tuple(options), sources=found.sources)

    # ── a brand with a generic ───────────────────────────────────────────────
    if is_brand and asked_cost and benchmark is not None:
        brand_month = asked_cost.per_unit * quantity
        sentences.append(f"Pharmacies pay about {money(brand_month)} a month for {name}, and about "
                         f"{money(benchmark)} for the generic, {generic.spoken}.")
        details.append(f"Brand: {_card_money(brand_month)}/mo · generic: {_card_money(benchmark)}/mo")
        if cheapest:
            sentences.append("For the generic: " + _where_to_buy(cash_opt, sub_opt))
            details.append(f"{cheapest.label}: {_card_money(cheapest.monthly)}/mo")
            sentences.append(CASH_CAVEAT)
        sentences.append("Ask your pharmacist or doctor whether the generic is right for you.")
        if negotiated:
            sentences.append(f"With Medicare, the negotiated price for {asked.brand} is "
                             f"{money(negotiated.price_30_day)} a month this year.")
        elif coming:
            sentences.append(_coming(coming).format(brand=asked.brand))
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
        sentences.append(CASH_CAVEAT)
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
            sentences.append(CASH_CAVEAT)
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
