"""
Medicare facts for 2026, each with the document it came from.

These change once a year at most, so they are data rather than calls. Every
number here was copied from the cited source; nothing is estimated.
"""

from __future__ import annotations

from dataclasses import dataclass

YEAR = 2026

# Out-of-pocket cap on covered Part D drugs, including Medicare Advantage drug
# coverage. Past it, the plan pays in full for the rest of the year.
PART_D_CAP = 2100
PART_D_CAP_SOURCE = "https://www.medicare.gov/health-drug-plans/part-d/basics/costs"

# Insulin covered by Part D: at most $35 for a month's supply.
INSULIN_MONTHLY_CAP = 35

# Since October 2018 two laws ban the contract clauses that stopped pharmacists
# telling patients when paying cash is cheaper than using insurance: the Know
# the Lowest Price Act (Medicare Part D and Advantage) and the Patient Right to
# Know Drug Prices Act (employer and marketplace plans). So "ask the pharmacist
# whether cash is cheaper" is advice a pharmacist is free to answer.
GAG_CLAUSE_BAN_SOURCE = ("https://news.ashp.org/news/ashp-news/2018/10/10/"
                         "pharmacists-now-can-tell-insured-patients-about-lower-cost-option")

NEGOTIATED_SOURCE = ("https://www.cms.gov/files/document/"
                     "fact-sheet-negotiated-prices-initial-price-applicability-year-2026.pdf")


@dataclass(frozen=True)
class NegotiatedPrice:
    brand: str
    names: tuple[str, ...]        # every brand name the price covers, lower case
    price_30_day: float           # Maximum Fair Price, 30-day supply, 2026
    list_price_30_day_2023: float


# CMS, "Negotiated Prices for Initial Price Applicability Year 2026" (Aug 2024).
# This is what Medicare pays for the drug, not what a patient pays at the
# counter; that depends on the plan. It lowers a patient's cost directly only
# where the plan charges a percentage (coinsurance) rather than a flat copay.
NEGOTIATED_2026: tuple[NegotiatedPrice, ...] = (
    NegotiatedPrice("Januvia", ("januvia",), 113.00, 527.00),
    NegotiatedPrice("NovoLog / Fiasp", ("novolog", "fiasp"), 119.00, 495.00),
    NegotiatedPrice("Farxiga", ("farxiga",), 178.50, 556.00),
    NegotiatedPrice("Enbrel", ("enbrel",), 2355.00, 7106.00),
    NegotiatedPrice("Jardiance", ("jardiance",), 197.00, 573.00),
    NegotiatedPrice("Stelara", ("stelara",), 4695.00, 13836.00),
    NegotiatedPrice("Xarelto", ("xarelto",), 197.00, 517.00),
    NegotiatedPrice("Eliquis", ("eliquis",), 231.00, 521.00),
    NegotiatedPrice("Entresto", ("entresto",), 295.00, 628.00),
    NegotiatedPrice("Imbruvica", ("imbruvica",), 9319.00, 14934.00),
)


def negotiated_for(brand: str | None) -> NegotiatedPrice | None:
    if not brand:
        return None
    b = brand.strip().lower()
    return next((n for n in NEGOTIATED_2026 if any(b == x or b.startswith(x + " ") for x in n.names)), None)
