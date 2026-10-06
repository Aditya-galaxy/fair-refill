"""
The simulator's stand-in for Alexa+: from what was said to which tool to call.

In production Alexa+'s own model does this, choosing among the add-on's tools
from their descriptions. Alexa+'s developer tools aren't open to hackathon
entrants, so the simulator routes with these rules instead — small, tested,
and reliable enough to demo live. The add-on itself (server.py) is the real
thing either way; this only decides which of its tools a sentence means.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}


@dataclass
class State:
    """What the conversation remembers between turns (kept by the page)."""
    choices: list[dict[str, str]] = field(default_factory=list)   # offered at the last "which one?"
    medicine: dict[str, str] | None = None                          # the last medicine priced
    you_pay: float | None = None
    quantity: int = 30

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> State:
        d = d or {}
        return cls(choices=list(d.get("choices") or []), medicine=d.get("medicine"),
                   you_pay=d.get("you_pay"), quantity=int(d.get("quantity") or 30))


def _words_to_digits(text: str) -> str:
    """"forty five dollars" → "45 dollars", "twenty" → "20"."""
    def repl(m: re.Match[str]) -> str:
        words = m.group(0).lower().replace("-", " ").split()
        return str(sum(_NUMBER_WORDS[w] for w in words))
    pattern = r"\b(?:" + "|".join(_NUMBER_WORDS) + r")(?:[ -](?:" + "|".join(_NUMBER_WORDS) + r"))?\b"
    return re.sub(pattern, repl, text, flags=re.IGNORECASE)


def money_said(text: str) -> float | None:
    text = _words_to_digits(text)
    m = re.search(r"\$\s?(\d+(?:\.\d{1,2})?)", text) or \
        re.search(r"(\d+(?:\.\d{1,2})?)\s*(?:dollars?|bucks)", text, flags=re.IGNORECASE)
    return float(m.group(1)) if m else None


def quantity_said(text: str) -> int | None:
    t = _words_to_digits(text.lower())
    if m := re.search(r"(\d+)\s*(?:tablets?|pills?|capsules?)\s*(?:a|per|each)\s*month", t):
        return int(m.group(1))
    for phrase, n in (("four times a day", 120), ("three times a day", 90), ("twice a day", 60),
                      ("two times a day", 60), ("once a day", 30), ("every day", 30), ("daily", 30)):
        if phrase in t:
            return n
    return None


_FILLER = re.compile(
    r"\b(alexa|ask|fair refill|am i|are you|i'?m|i am|i|over ?paying|paying|pay|too much|how much|should|does|"
    r"do|is|it|cost|costs|price|prices|for|my|the|a|an|of|per|each|every|month|months|monthly|what'?s|what|can|get|"
    r"cheaper|cheap|way|to|me|tell|about|check|much|in|on|with|and|any|dollars?|bucks|tablets? a month|"
    r"once a day|twice a day|three times a day|daily|every day|please|if|whether|that|there|some|now|"
    r"currently|right|really|actually|still|will|would|going|be|next|this|year|from|january|medicare'?s?|"
    r"negotiated|new|soon)\b", re.IGNORECASE)


def medicine_said(text: str) -> str:
    """What's left of a sentence once the talking-about-it words are gone."""
    t = _words_to_digits(text)
    t = re.sub(r"\$\s?\d+(?:\.\d{1,2})?", " ", t)
    t = re.sub(r"(\d+(?:\.\d{1,2})?)\s*(?:dollars?|bucks)", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"(\d+)\s*(?:tablets?|pills?|capsules?)\s*(?:a|per|each)\s*month", " ", t, flags=re.IGNORECASE)
    t = _FILLER.sub(" ", t)
    t = re.sub(r"[?.,!']", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _pick(text: str, choices: list[dict[str, str]]) -> dict[str, str] | None:
    """Which offered option someone means: "the regular one", "extended
    release", "the 20 milligram", "the second one"."""
    t = _words_to_digits(text.lower())
    for word, index in (("first", 0), ("second", 1), ("third", 2), ("fourth", 3), ("fifth", 4), ("last", -1)):
        if re.search(rf"\b{word}\b", t) and choices:
            return choices[index] if abs(index) <= len(choices) else None
    if re.search(r"\b(extended|er|xr|slow)\b", t):
        return next((c for c in choices if "extended-release" in c["name"]), None)
    if re.search(r"\b(regular|normal|plain|immediate|ordinary|standard)\b", t):
        plain = [c for c in choices if not re.search(r"(extended|delayed)-release", c["name"])]
        return plain[0] if len(plain) == 1 else None
    numbers = re.findall(r"\d+(?:\.\d+)?", t)
    if numbers:
        hits = [c for c in choices if any(re.search(rf"(?<![\d.]){n} (mg|mcg)", c["name"]) for n in numbers)]
        return hits[0] if len(hits) == 1 else None
    for c in choices:                              # a distinctive word from the option itself
        words = set(c["name"].lower().split()) - {"mg", "tablet", "capsule"}
        if any(w in t.split() for w in words if len(w) > 3):
            others = [o for o in choices if o is not c and any(w in o["name"].lower() for w in t.split())]
            if not others:
                return c
    return None


def route(text: str, state: State) -> tuple[str, dict[str, Any]]:
    """(tool, arguments), or ("say", {"speech": …}) when nothing needs calling."""
    t = text.lower().strip()
    you_pay = money_said(text)
    quantity = quantity_said(text)

    if state.choices:
        chosen = _pick(text, state.choices)
        if chosen:
            args: dict[str, Any] = {"choice_id": chosen["choice_id"], "monthly_quantity": quantity or state.quantity}
            if (you_pay or state.you_pay) is not None:
                args["you_pay_per_month"] = you_pay if you_pay is not None else state.you_pay
            return "check_chosen_medicine", args

    if re.search(r"\b(all|every|any) (of )?my (medicines|medications|prescriptions|pills|meds)\b|"
                 r"\bgo through my list\b|\bcheck my list\b", t):
        return "check_all_my_medicines", {}
    if re.search(r"\bwhat'?s on my list\b|\bwhat (medicines|meds) (have i|did i) (saved|save)\b|\bread my list\b", t):
        return "list_my_medicines", {}
    if re.search(r"\b(remember|save|add)\b.*\b(it|this|that|list)\b|\bremember (this|it|that)\b", t):
        if state.medicine:
            args = {"choice_id": state.medicine["choice_id"], "monthly_quantity": quantity or state.quantity}
            if (you_pay or state.you_pay) is not None:
                args["you_pay_per_month"] = you_pay if you_pay is not None else state.you_pay
            return "save_my_medicine", args
        return "say", {"speech": "Check a medicine's price first, then ask me to remember it."}
    if re.search(r"\b(remove|delete|forget)\b|\bdon'?t take\b|\bno longer take\b|\bstopped taking\b", t):
        return "remove_my_medicine", {"choice_id": (state.medicine or {}).get("choice_id", ""),
                                      "_by_name": medicine_said(re.sub(r"\b(remove|delete|forget|from|list|"
                                                                       r"don'?t|no longer|stopped|taking|"
                                                                       r"take|anymore|any more)\b", " ", t))}
    if re.search(r"\bmedicare\b.*\b(limit|cap|max|maximum|most)\b|\b(limit|cap)\b.*\bmedicare\b|"
                 r"\bout[- ]of[- ]pocket (limit|cap|max)", t):
        return "medicare_drug_cost_limits", {}

    medicine = medicine_said(text)
    if not medicine:
        return "say", {"speech": "Which medicine should I check? Say its name, and what you pay "
                                 "a month if you know it."}
    args = {"medicine": medicine, "monthly_quantity": quantity or 30}
    if you_pay is not None:
        args["you_pay_per_month"] = you_pay
    return "check_prescription_price", args
