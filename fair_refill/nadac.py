"""
What pharmacies actually pay: CMS's National Average Drug Acquisition Cost.

NADAC is a weekly survey of what retail pharmacies pay wholesalers, per unit
(tablet, ml, gram), for each NDC. It is the closest thing to a public "real
cost" of a medicine, and it's what the add-on compares a person's price with.
It is *not* a price anyone can buy at — the answers always say "pharmacies
pay", never "you can pay".

Each weekly publication (`as_of_date`) repeats every rate in force, so the
current price for an NDC is its row in the latest publication, not the row
with the latest effective date.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from .http import Http

QUERY = "https://data.medicaid.gov/api/1/datastore/query/{dataset}/0"
# "NADAC (National Average Drug Acquisition Cost) 2026". CMS starts a new
# dataset each year; a new year means a new ID here.
DATASET_2026 = "fbb83258-11c7-47f5-8b18-5f8e79f7e704"
_CHUNK = 150                      # NDCs per query; the rows of one week stay under the 500 limit


@dataclass(frozen=True)
class NadacPrice:
    per_unit: float               # median across the drug's priced NDCs
    low: float
    high: float
    unit: str                     # EA (each), ML, GM
    ndcs_priced: int
    as_of: str                    # publication date, YYYY-MM-DD
    generic_per_unit: float | None    # for brand rows: CMS's figure for the generic equivalent


class Nadac:
    def __init__(self, http: Http, dataset: str = DATASET_2026) -> None:
        self.http = http
        self.url = QUERY.format(dataset=dataset)
        self._as_of: str | None = None

    def latest_as_of(self) -> str:
        if self._as_of is None:
            data = self.http.post(self.url, {"limit": 1, "properties": ["as_of_date"],
                                             "sorts": [{"property": "as_of_date", "order": "desc"}]})
            self._as_of = data["results"][0]["as_of_date"]
        return self._as_of

    def price(self, ndcs: list[str]) -> NadacPrice | None:
        if not ndcs:
            return None
        as_of = self.latest_as_of()
        rows: list[dict] = []
        for i in range(0, len(ndcs), _CHUNK):
            data = self.http.post(self.url, {
                "conditions": [{"property": "ndc", "value": ndcs[i:i + _CHUNK], "operator": "in"},
                               {"property": "as_of_date", "value": as_of, "operator": "="}],
                "properties": ["ndc", "nadac_per_unit", "pricing_unit",
                               "corresponding_generic_drug_nadac_per_unit"],
                "limit": 500,
            })
            rows.extend(data.get("results") or [])
        if not rows:
            return None
        units = {r["pricing_unit"] for r in rows}
        unit = max(units, key=lambda u: sum(r["pricing_unit"] == u for r in rows))
        prices = [float(r["nadac_per_unit"]) for r in rows if r["pricing_unit"] == unit]
        generic = [float(r["corresponding_generic_drug_nadac_per_unit"]) for r in rows
                   if r.get("corresponding_generic_drug_nadac_per_unit")]
        return NadacPrice(per_unit=statistics.median(prices), low=min(prices), high=max(prices), unit=unit,
                          ndcs_priced=len({r["ndc"] for r in rows}), as_of=as_of,
                          generic_per_unit=statistics.median(generic) if generic else None)
