"""
A real cash price anyone can buy at: Mark Cuban Cost Plus Drug Company.

Cost Plus publishes its prices through a public API. A quote counts only if
its NDC is one of the NDCs RxNorm lists for the exact drug in question — a
name match is not enough, because "metformin 500mg" can be an immediate- or
extended-release tablet, and those are different medicines.

A quote is the medicine plus Cost Plus's $5.00 pharmacy fee, both charged per
fill. Shipping is extra and charged per order, so it is added here before any
price is said: what someone compares with their copay has to be what arrives
at their door. The fee and the shipping are per fill and per order, not per
tablet, which is why three months at once costs far less per month.
"""

from __future__ import annotations

from dataclasses import dataclass

from .http import Http

URL = "https://us-central1-costplusdrugs-publicapi.cloudfunctions.net/main"

# "Standard Shipping, additional cost at checkout: $5.25", from the price
# breakdown on Cost Plus's own medicine pages, read on 2026-10-06. Tax, where
# a state charges it, is not included.
SHIPPING = 5.25
SHIPPING_CHECKED = "2026-10-06"
LONG_SUPPLY_MONTHS = 3            # the longer fill compared with a month at a time


@dataclass(frozen=True)
class Quote:
    ndc: str
    total: float                  # for `quantity` units, with the pharmacy fee, before shipping
    quantity: int
    url: str

    def delivered(self, units: int) -> float:
        """What `units` cost in one order, at the door."""
        return self.total * units / self.quantity + SHIPPING


def _money(text: str) -> float:
    return float(text.replace("$", "").replace(",", ""))


class CostPlus:
    def __init__(self, http: Http) -> None:
        self.http = http

    def quote(self, ingredient: str, strength: str | None, quantity: int,
              allowed_ndcs: set[str]) -> Quote | None:
        """The cheapest quote for the identical drug, or None."""
        found = self._quote(ingredient, strength, quantity, allowed_ndcs)
        if found:
            return found
        # Cost Plus's search wants its own name exactly, and it names many
        # medicines by salt or release: "Metoprolol Tartrate", "Pantoprazole
        # Sodium", "Omeprazole Delayed Release (DR)". Searching "metoprolol"
        # finds nothing. Its catalogue says which name and strength it sells
        # the identical packages under, so ask again by that.
        for name, sold_as in self._sold_as(allowed_ndcs):
            found = self._quote(name, sold_as, quantity, allowed_ndcs)
            if found:
                return found
        return None

    def _quote(self, name: str, strength: str | None, quantity: int, allowed_ndcs: set[str]) -> Quote | None:
        params: dict[str, str | int] = {"medication_name": name, "quantity_units": quantity}
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

    def _sold_as(self, allowed_ndcs: set[str]) -> list[tuple[str, str | None]]:
        """(Cost Plus's name, its strength) for any of these packages it sells.
        The whole catalogue is one request, kept as long as any price."""
        data = self.http.get(URL)
        return sorted({(r["medication_name"], r.get("strength") or None) for r in data.get("results") or []
                       if (r.get("ndc") or "").replace("-", "") in allowed_ndcs and r.get("medication_name")})
