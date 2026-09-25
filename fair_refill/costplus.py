"""
A real cash price anyone can buy at: Mark Cuban Cost Plus Drug Company.

Cost Plus publishes its prices through a public API. A quote counts only if
its NDC is one of the NDCs RxNorm lists for the exact drug in question — a
name match is not enough, because "metformin 500mg" can be an immediate- or
extended-release tablet, and those are different medicines.

Quotes exclude shipping, and every answer that uses one says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from .http import Http

URL = "https://us-central1-costplusdrugs-publicapi.cloudfunctions.net/main"


@dataclass(frozen=True)
class Quote:
    ndc: str
    total: float                  # for `quantity` units, before shipping
    quantity: int
    url: str


def _money(text: str) -> float:
    return float(text.replace("$", "").replace(",", ""))


class CostPlus:
    def __init__(self, http: Http) -> None:
        self.http = http

    def quote(self, ingredient: str, strength: str | None, quantity: int,
              allowed_ndcs: set[str]) -> Quote | None:
        """The cheapest quote for the identical drug, or None."""
        params: dict[str, str | int] = {"medication_name": ingredient, "quantity_units": quantity}
        if strength:
            params["strength"] = strength
        data = self.http.get(URL, params)
        quotes = []
        for r in data.get("results") or []:
            ndc = (r.get("ndc") or "").replace("-", "")
            if ndc not in allowed_ndcs or not r.get("requested_quote"):
                continue
            quotes.append(Quote(ndc=ndc, total=_money(r["requested_quote"]),
                                quantity=int(r.get("requested_quote_units") or quantity), url=r.get("url", "")))
        return min(quotes, key=lambda q: q.total) if quotes else None
