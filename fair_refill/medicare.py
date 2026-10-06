"""
Medicare facts for 2026, each with the document it came from.

These change once a year at most, so they are data rather than calls. Every
number here was copied from the cited source; nothing is estimated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

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
NEGOTIATED_2027_SOURCE = "https://www.cms.gov/files/document/fact-sheet-negotiated-prices-ipay-2027.pdf"

# Medicare's yearly open enrollment: 15 October to 7 December, for coverage
# that starts 1 January. It's when someone can change plans, so it's when a
# price that starts in January is worth knowing about.
OPEN_ENROLLMENT_SOURCE = "https://www.medicare.gov/basics/get-started-with-medicare/get-more-coverage/joining-a-plan"


@dataclass(frozen=True)
class NegotiatedPrice:
    brand: str
    names: tuple[str, ...]        # every brand name the price covers, lower case
    price_30_day: float           # Maximum Fair Price, 30-day supply, as CMS published it
    list_price_30_day: float      # the list price CMS compares it with
    starts: date                  # the day the price takes effect
    source: str


# CMS, "Negotiated Prices for Initial Price Applicability Year 2026" (Aug 2024).
# This is what Medicare pays for the drug, not what a patient pays at the
# counter; that depends on the plan. It lowers a patient's cost directly only
# where the plan charges a percentage (coinsurance) rather than a flat copay.
# The list prices are 2023's.
_2026 = (date(2026, 1, 1), NEGOTIATED_SOURCE)
NEGOTIATED_2026: tuple[NegotiatedPrice, ...] = (
    NegotiatedPrice("Januvia", ("januvia",), 113.00, 527.00, *_2026),
    NegotiatedPrice("NovoLog / Fiasp", ("novolog", "fiasp"), 119.00, 495.00, *_2026),
    NegotiatedPrice("Farxiga", ("farxiga",), 178.50, 556.00, *_2026),
    NegotiatedPrice("Enbrel", ("enbrel",), 2355.00, 7106.00, *_2026),
    NegotiatedPrice("Jardiance", ("jardiance",), 197.00, 573.00, *_2026),
    NegotiatedPrice("Stelara", ("stelara",), 4695.00, 13836.00, *_2026),
    NegotiatedPrice("Xarelto", ("xarelto",), 197.00, 517.00, *_2026),
    NegotiatedPrice("Eliquis", ("eliquis",), 231.00, 521.00, *_2026),
    NegotiatedPrice("Entresto", ("entresto",), 295.00, 628.00, *_2026),
    NegotiatedPrice("Imbruvica", ("imbruvica",), 9319.00, 14934.00, *_2026),
)

# CMS, "Negotiated Prices for Initial Price Applicability Year 2027" (Nov 2025):
# fifteen more drugs, from 1 January 2027. The list prices are 2024's. One
# figure covers every form of a drug, so it is CMS's price for a typical
# 30-day supply: a package of one strength can differ (CMS's own example is
# $385.63 for four Wegovy 2.4 mg pens against the $274 below).
_2027 = (date(2027, 1, 1), NEGOTIATED_2027_SOURCE)
NEGOTIATED_2027: tuple[NegotiatedPrice, ...] = (
    NegotiatedPrice("Ozempic / Rybelsus / Wegovy", ("ozempic", "rybelsus", "wegovy"), 274.00, 959.00, *_2027),
    NegotiatedPrice("Trelegy Ellipta", ("trelegy ellipta", "trelegy"), 175.00, 654.00, *_2027),
    NegotiatedPrice("Xtandi", ("xtandi",), 7004.00, 13480.00, *_2027),
    NegotiatedPrice("Pomalyst", ("pomalyst",), 8650.00, 21744.00, *_2027),
    NegotiatedPrice("Ofev", ("ofev",), 6350.00, 12622.00, *_2027),
    NegotiatedPrice("Ibrance", ("ibrance",), 7871.00, 15741.00, *_2027),
    NegotiatedPrice("Linzess", ("linzess",), 136.00, 539.00, *_2027),
    NegotiatedPrice("Calquence", ("calquence",), 8600.00, 14228.00, *_2027),
    NegotiatedPrice("Austedo", ("austedo", "austedo xr"), 4093.00, 6623.00, *_2027),
    NegotiatedPrice("Breo Ellipta", ("breo ellipta", "breo"), 67.00, 397.00, *_2027),
    NegotiatedPrice("Xifaxan", ("xifaxan",), 1000.00, 2696.00, *_2027),
    NegotiatedPrice("Vraylar", ("vraylar",), 770.00, 1376.00, *_2027),
    NegotiatedPrice("Tradjenta", ("tradjenta",), 78.00, 488.00, *_2027),
    NegotiatedPrice("Janumet", ("janumet", "janumet xr"), 80.00, 526.00, *_2027),
    NegotiatedPrice("Otezla", ("otezla", "otezla xr"), 1650.00, 4722.00, *_2027),
)

_ALL = NEGOTIATED_2026 + NEGOTIATED_2027


def _find(brand: str | None) -> NegotiatedPrice | None:
    if not brand:
        return None
    b = brand.strip().lower()
    return next((n for n in _ALL if any(b == x or b.startswith(x + " ") for x in n.names)), None)


def negotiated_for(brand: str | None, today: date | None = None) -> NegotiatedPrice | None:
    """The negotiated price in force today, exactly as CMS published it.

    A published figure holds for its first year only: each year after, CMS
    raises it with inflation and publishes the new one. So past that first
    year this returns nothing until the new figures are entered above; a
    price that is a year out of date is worse than none."""
    today = today or date.today()
    found = _find(brand)
    return found if found and found.starts.year == today.year and found.starts <= today else None


def upcoming_for(brand: str | None, today: date | None = None) -> NegotiatedPrice | None:
    """A negotiated price that has been published but hasn't started yet."""
    today = today or date.today()
    found = _find(brand)
    return found if found and found.starts > today else None


def open_enrollment(today: date | None = None) -> bool:
    """Whether Medicare's open enrollment (15 October to 7 December) is on."""
    today = today or date.today()
    return date(today.year, 10, 15) <= today <= date(today.year, 12, 7)
