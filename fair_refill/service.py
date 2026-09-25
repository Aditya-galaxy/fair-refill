"""
From what someone said to an answer: find the drug, fetch its prices, assess.

This is the one place that talks to all three sources, and the one place the
MCP tools call. Independent fetches run in parallel, because a cold lookup
touches three public APIs and a person is waiting on a spoken reply.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .compare import Finding, assess, cannot_compare, comparable_form
from .costplus import CostPlus
from .http import Http, SourceUnavailable
from .nadac import Nadac
from .rxnorm import Drug, RxNorm

MAX_CHOICES = 5          # Alexa+ voice guidance: offer at most five options at a time


@dataclass(frozen=True)
class Result:
    kind: str                                   # answer | choose | not_found | unavailable
    speech: str
    finding: Finding | None = None
    choices: tuple[Drug, ...] = field(default=())
    corrected: str | None = None


class PriceCheck:
    def __init__(self, http: Http | None = None, cache_dir: Path | None = None) -> None:
        self.http = http or Http(cache_dir=cache_dir)
        self.rx = RxNorm(self.http)
        self.nadac = Nadac(self.http)
        self.costplus = CostPlus(self.http)

    def find(self, text: str) -> Result:
        try:
            found, corrected = self.rx.search(text)
        except SourceUnavailable:
            return Result("unavailable", "I can't reach the medicine database right now. Try again in a minute.")
        if not found:
            return Result("not_found", f"I couldn't find a medicine called {text}. "
                                       "Try the name on the label, and the strength if you know it.")
        if not any(comparable_form(d.form) for d in found):
            # No point asking which inhaler it is only to say inhalers can't be
            # compared yet: say so straight away.
            finding = cannot_compare(found[0])
            return Result("answer", finding.speech, finding=finding, choices=(found[0],), corrected=corrected)
        if len(found) > 1:
            shown = found[:MAX_CHOICES]
            said = [d.spoken for d in shown]
            # Speak only what differs: "10, 20 or 40 mg tablet" reads better as
            # the options themselves once the shared words are said once.
            prefix = os.path.commonprefix(said)
            prefix = prefix[: prefix.rfind(" ") + 1] if " " in prefix else ""
            tails = [x[len(prefix):] for x in said] if prefix else said
            # "extended-release tablet, or tablet" → "…, or regular tablet"
            tails = [f"regular {t}" if t in ("tablet", "capsule") and any(u.endswith(t) and u != t for u in tails)
                     else t for t in tails]
            listed = ", ".join(tails[:-1]) + f", or {tails[-1]}"
            lead = f"Which {prefix.strip()} do you take" if prefix else "Which one do you take"
            more = " There are more options too." if len(found) > MAX_CHOICES else ""
            return Result("choose", f"{lead}: {listed}?{more}", choices=tuple(shown), corrected=corrected)
        return Result("answer", "", choices=(found[0],), corrected=corrected)

    def check(self, drug: Drug, quantity: int = 30, you_pay: float | None = None) -> Result:
        try:
            generic = self.rx.generic_of(drug)
            with ThreadPoolExecutor(max_workers=3) as pool:
                asked_ndcs_f = pool.submit(self.rx.ndcs, drug.rxcui)
                generic_ndcs_f = pool.submit(self.rx.ndcs, generic.rxcui) if generic.rxcui != drug.rxcui \
                    else asked_ndcs_f
                asked_ndcs, generic_ndcs = asked_ndcs_f.result(), generic_ndcs_f.result()
                asked_cost_f = pool.submit(self.nadac.price, asked_ndcs)
                generic_cost_f = pool.submit(self.nadac.price, generic_ndcs) if generic_ndcs is not asked_ndcs \
                    else asked_cost_f
                cash_f = pool.submit(self.costplus.quote, generic.ingredient, generic.strength_token, quantity,
                                     set(generic_ndcs))
                asked_cost, generic_cost, cash = asked_cost_f.result(), generic_cost_f.result(), cash_f.result()
        except SourceUnavailable:
            return Result("unavailable", "One of the price sources isn't answering right now. "
                                         "Try again in a minute.", choices=(drug,))
        finding = assess(asked=drug, generic=generic, quantity=quantity, asked_cost=asked_cost,
                         generic_cost=generic_cost, cash=cash, you_pay=you_pay)
        return Result("answer", finding.speech, finding=finding, choices=(drug,))

    def ask(self, text: str, quantity: int = 30, you_pay: float | None = None) -> Result:
        """One step when the medicine is unambiguous; a question when it isn't."""
        found = self.find(text)
        if found.kind != "answer" or found.finding is not None:
            return found
        result = self.check(found.choices[0], quantity, you_pay)
        if found.corrected and result.kind == "answer":
            return Result(result.kind, f"I found {found.choices[0].spoken}. " + result.speech,
                          finding=result.finding, choices=result.choices, corrected=found.corrected)
        return result
