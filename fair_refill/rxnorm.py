"""
Which exact medicine someone means, from the way they'd say it.

RxNorm (US National Library of Medicine) names every medicine at the level
that matters for price: ingredient, strength and dose form. "Lipitor 20" and
"atorvastatin 20 mg" are two products (a branded drug, SBD, and a clinical
drug, SCD) of one clinical drug, and RxNorm links them. Every package on a
pharmacy shelf has an NDC, and RxNorm lists the NDCs of each clinical drug.

That link is what makes a price comparison honest: two prices are compared
only when both are for NDCs of the same clinical drug. Never "a similar
medicine", never a different strength.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .http import Http

BASE = "https://rxnav.nlm.nih.gov/REST"

_STRENGTH = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|unit|units|%)\b", re.IGNORECASE)
# People say "Lipitor 20" as often as "Lipitor 20 milligrams".
_BARE_NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])")
_BRAND = re.compile(r"\[([^\]]+)\]\s*$")

# How a person would say a dose form out loud.
_SPOKEN_FORMS = (
    ("Extended Release Oral Tablet", "extended-release tablet"),
    ("Delayed Release Oral Capsule", "delayed-release capsule"),
    ("Delayed Release Oral Tablet", "delayed-release tablet"),
    ("Extended Release Oral Capsule", "extended-release capsule"),
    ("Chewable Tablet", "chewable tablet"),
    ("Oral Tablet", "tablet"),
    ("Oral Capsule", "capsule"),
    ("Oral Solution", "liquid"),
    ("Oral Suspension", "liquid"),
    ("Metered Dose Inhaler", "inhaler"),
    ("Dry Powder Inhaler", "dry-powder inhaler"),
    ("Pen Injector", "injection pen"),
    ("Prefilled Syringe", "prefilled syringe"),
    ("Injectable Solution", "injection"),
    ("Topical Cream", "cream"),
    ("Topical Ointment", "ointment"),
)


@dataclass(frozen=True)
class Drug:
    rxcui: str
    name: str             # RxNorm's name, e.g. "atorvastatin 20 MG Oral Tablet [Lipitor]"
    tty: str              # SCD (clinical drug) or SBD (branded drug)
    # For drugs RxNorm lists per approved product — inhalers, mostly — the
    # brand whose product this is: "Ventolin" for the Ventolin-type generic.
    # A label for saying it, never part of which drug it is.
    family: str | None = None

    @property
    def brand(self) -> str | None:
        m = _BRAND.search(self.name)
        return m.group(1) if m else None

    @property
    def spoken(self) -> str:
        """"atorvastatin 20 mg tablet" / "Lipitor 20 mg tablet" — the way it's said aloud."""
        base = _BRAND.sub("", self.name).strip()
        # Release-mechanism prefixes and salt names are pharmacy detail, not
        # how anyone says a medicine: "metformin 500 mg extended-release tablet".
        base = re.sub(r"^(?:(?:Modified|Osmotic|Biphasic)\s+)?\d+\s*HR\s+", "", base)
        base = _PRODUCT_SPECIFIC.sub("", base)
        puffs = re.match(r"^(\d+)\s*ACTUAT\s+", base)
        base = re.sub(r"^\d+\s*ACTUAT\s+", "", base)                       # "200 ACTUAT" = puffs per inhaler
        base = re.sub(r"(\d+(?:\.\d+)?)\s*MG/ACTUAT",
                      lambda m: f"{round(float(m.group(1)) * 1000):g} mcg per puff", base)
        base = re.sub(r"\s(hydrochloride|HCl|sodium|potassium|calcium|besylate|maleate|succinate|tartrate|"
                      r"mesylate|citrate|sulfate|phosphate|acetate|bromide|magnesium)\b", "", base,
                      flags=re.IGNORECASE)
        for form, said in _SPOKEN_FORMS:
            if base.endswith(form):
                base = base[: -len(form)].strip() + " " + said
                break
        base = re.sub(r"\b(MG|MCG|ML|UNT|UNITS?)\b", lambda m: {"UNT": "units"}.get(m.group(1), m.group(1).lower()),
                      base)
        base = base.replace("/ML", " per ml").replace(" / ", " and ")
        if self.brand:
            ingredient = base.split(" ")[0]
            base = base.replace(ingredient, self.brand, 1)
        if self.family and not self.brand:
            base += f", {self.family} type"
        if puffs:
            base += f", {puffs.group(1)} puffs"
        return re.sub(r"\s+", " ", base).strip()

    @property
    def strength_token(self) -> str | None:
        """"20mg" — how Cost Plus writes a strength."""
        m = _STRENGTH.search(self.name)
        return f"{m.group(1)}{m.group(2).lower()}" if m else None

    @property
    def ingredient(self) -> str:
        """The first ingredient, as Cost Plus names medicines."""
        base = _PRODUCT_SPECIFIC.sub("", _BRAND.sub("", self.name).strip())
        base = re.sub(r"^(?:(?:Modified|Osmotic|Biphasic)\s+)?\d+\s*HR\s+|^\d+\s*ACTUAT\s+", "", base)
        return base.split(" ")[0].lower()

    @property
    def ingredients(self) -> frozenset[str]:
        """{"amlodipine", "olmesartan"}: the first word before each strength."""
        base = _PRODUCT_SPECIFIC.sub("", _BRAND.sub("", self.name).strip())
        base = re.sub(r"^(?:(?:Modified|Osmotic|Biphasic)\s+)?\d+\s*HR\s+|^\d+\s*ACTUAT\s+", "", base)
        found = set()
        for part in base.split(" / "):
            m = re.match(r"([A-Za-z][A-Za-z\- ]*?)\s+\d", part)
            if m:
                found.add(m.group(1).split(" ")[0].lower())
        return frozenset(found)

    @property
    def form(self) -> str:
        """The dose form as said aloud: "tablet", "extended-release tablet"."""
        base = _BRAND.sub("", self.name).strip()
        for rx_form, said in _SPOKEN_FORMS:
            if base.endswith(rx_form):
                return said
        return base.rsplit(" ", 1)[-1].lower()


# Words people use for a dose form, and the RxNorm text each one stands for.
_FORM_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (r"\binhalers?\b|\bpuffers?\b", ("Inhaler",)),
    (r"\bnebuli[sz]er\b", ("Inhalation Solution",)),
    (r"\bcreams?\b", ("Cream",)),
    (r"\bointments?\b", ("Ointment",)),
    (r"\b(injections?|shots?)\b", ("Inject",)),
    (r"\bpens?\b", ("Pen Injector", "Auto-Injector")),
    (r"\b(liquid|syrup|solution|suspension)\b", ("Oral Solution", "Oral Suspension")),
    (r"\b(extended[- ]release|er|xr|xl|sr)\b", ("Extended Release",)),
    (r"\bpatch(es)?\b", ("Transdermal",)),
    (r"\b(eye )?drops\b", ("Ophthalmic",)),
)


def form_hint(text: str) -> tuple[str, tuple[str, ...] | None]:
    """The text with any dose-form words removed, and what they asked for."""
    for pattern, forms in _FORM_HINTS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return re.sub(pattern, " ", text, flags=re.IGNORECASE), forms
    return text, None


def split_query(text: str) -> tuple[str, str | None]:
    """("atorvastatin", "20 mg") from "atorvastatin 20mg", and ("lipitor", "20")
    from "Lipitor 20" — a strength with no unit matches any unit. The name is
    the words before the first number."""
    # Speech recognition writes units out: "10 milligrams", "90 micrograms".
    text = re.sub(r"\bmilligrams?\b", "mg", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\bmicrograms?\b", "mcg", text, flags=re.IGNORECASE)
    m = _STRENGTH.search(text)
    if m:
        strength: str | None = f"{m.group(1)} {m.group(2).lower()}"
        name = text[: m.start()]
    else:
        bare = _BARE_NUMBER.search(text)
        strength = bare.group(1) if bare else None
        name = text[: bare.start()] if bare else text
    name = re.sub(r"\b(tablets?|pills?|capsules?|mg|my|the|of)\b", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip(), strength


def _matches_strength(drug: Drug, strength: str) -> bool:
    number, _, unit = strength.partition(" ")
    unit = {"units": "unit"}.get(unit, unit)
    after = rf" {re.escape(unit)}\b" if unit else r" [A-Za-z]"
    return re.search(rf"(?<![\d.]){re.escape(number)}{after}", drug.name, flags=re.IGNORECASE) is not None


_PRODUCT_SPECIFIC = re.compile(r"^(?:NDA\d+|Sensor)\s+")


def _strength_order(d: Drug) -> float:
    m = _STRENGTH.search(d.name)
    return float(m.group(1)) if m else float("inf")


def _one_per_spoken_name(drugs: list[Drug]) -> list[Drug]:
    """RxNorm lists release mechanisms a person would never name ("Osmotic 24
    HR …", "Modified 24 HR …"). Offer one option per thing that can be said,
    and keep the plainest product behind it — the one most prescriptions are for."""
    best: dict[str, Drug] = {}
    for d in drugs:
        key = d.spoken.lower()
        if key not in best or len(d.name) < len(best[key].name):
            best[key] = d
    return list(best.values())


def _is_combination(drug: Drug) -> bool:
    return " / " in _BRAND.sub("", drug.name)


class RxNorm:
    def __init__(self, http: Http) -> None:
        self.http = http

    def _concepts(self, name: str) -> list[Drug]:
        data = self.http.get(f"{BASE}/drugs.json", {"name": name})
        out = []
        for group in (data.get("drugGroup") or {}).get("conceptGroup") or []:
            if group.get("tty") not in ("SCD", "SBD"):
                continue
            out.extend(Drug(p["rxcui"], p["name"], p["tty"]) for p in group.get("conceptProperties") or [])
        return out

    def _suggest(self, name: str) -> str | None:
        data = self.http.get(f"{BASE}/spellingsuggestions.json", {"name": name})
        found = ((data.get("suggestionGroup") or {}).get("suggestionList") or {}).get("suggestion") or []
        return found[0] if found else None

    def search(self, text: str) -> tuple[list[Drug], str | None]:
        """Candidate medicines for what was said, and the corrected name if the
        spelling was fixed. Brands come back as brands, generics as generics:
        someone who says "Lipitor" is asking about Lipitor."""
        text, forms = form_hint(text)
        name, strength = split_query(text)
        if not name:
            return [], None
        # RxNorm ignores case, and speech recognition capitalises as it
        # pleases: one spelling means one lookup, and one cached answer.
        name = name.lower()
        corrected = None
        concepts = self._concepts(name)
        if not concepts:
            corrected = self._suggest(name)
            concepts = self._concepts(corrected) if corrected else []
        said = (corrected or name).lower()
        asked_for_brand = any((d.brand or "").lower() == said for d in concepts)
        concepts = [d for d in concepts
                    if (d.tty == "SBD" and (d.brand or "").lower() == said) or (not asked_for_brand and d.tty == "SCD")]
        # Someone who names one medicine means the single-ingredient product,
        # not every combination pill that contains it.
        if len(said.split()) == 1:
            single = [d for d in concepts if not _is_combination(d)]
            concepts = single or concepts
        if strength:
            concepts = [d for d in concepts if _matches_strength(d, strength)]
        if forms:
            concepts = [d for d in concepts if any(f.lower() in d.name.lower() for f in forms)]
        elif any(" Extended Release " in f" {d.name} " for d in concepts) and \
                any("Extended Release" not in d.name for d in concepts):
            pass   # both kinds exist and nobody said which: the caller asks
        concepts = [self._with_family(d) for d in concepts]
        return sorted(_one_per_spoken_name(concepts), key=_strength_order), corrected

    def _with_family(self, drug: Drug) -> Drug:
        if drug.tty != "SCD" or not _PRODUCT_SPECIFIC.match(drug.name):
            return drug
        data = self.http.get(f"{BASE}/rxcui/{drug.rxcui}/related.json", {"tty": "SBD"})
        for group in (data.get("relatedGroup") or {}).get("conceptGroup") or []:
            for p in group.get("conceptProperties") or []:
                family = Drug(p["rxcui"], p["name"], "SBD").brand
                if family:
                    return Drug(drug.rxcui, drug.name, drug.tty, family)
        return drug

    def drug(self, rxcui: str) -> Drug | None:
        """The drug behind an ID handed out earlier, so a follow-up ("the
        regular tablet") refers to exactly what was offered."""
        if not rxcui.isdigit():
            return None
        data = self.http.get(f"{BASE}/rxcui/{rxcui}/properties.json")
        props = data.get("properties") if isinstance(data, dict) else None
        if not props or props.get("tty") not in ("SCD", "SBD"):
            return None
        return self._with_family(Drug(props["rxcui"], props["name"], props["tty"]))

    def generic_of(self, drug: Drug) -> Drug:
        """The clinical drug behind a brand: same ingredient, strength and form."""
        if drug.tty == "SCD":
            return drug
        data = self.http.get(f"{BASE}/rxcui/{drug.rxcui}/related.json", {"tty": "SCD"})
        for group in (data.get("relatedGroup") or {}).get("conceptGroup") or []:
            for p in group.get("conceptProperties") or []:
                return Drug(p["rxcui"], p["name"], "SCD")
        return drug

    def ndcs(self, rxcui: str) -> list[str]:
        data = self.http.get(f"{BASE}/rxcui/{rxcui}/ndcs.json")
        return list(((data.get("ndcGroup") or {}).get("ndcList") or {}).get("ndc") or [])
