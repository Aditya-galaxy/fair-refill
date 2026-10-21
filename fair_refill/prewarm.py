"""
Have the common answers ready before anyone asks.

    python -m fair_refill.prewarm           # one round, with timings

A cold price check touches three public APIs and takes 5 to 15 seconds, which
is a long silence after a spoken question. Most questions are about a small
set of medicines, so the server looks those up when it starts and again every
few hours, through the same cache a live question reads (http.py). A warm
check answers from disk.

Nothing here changes an answer. A pre-warmed price is the source's own
response, kept for at most the time any cached response is kept, and it still
carries the source's date when it's spoken.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import httpx

from .compare import comparable_form
from .http import Http, SourceUnavailable
from .service import PriceCheck

ROOT = Path(__file__).resolve().parent.parent

# Widely prescribed tablets and capsules, then brands Medicare has negotiated
# prices for, in force or starting in January (medicare.py), and a few brands
# people name instead of the generic. Every strength of each is warmed. Order matters only in that the
# first ones are ready first.
MEDICINES: tuple[str, ...] = (
    "atorvastatin", "lisinopril", "metformin", "amlodipine", "levothyroxine", "metoprolol", "losartan",
    "omeprazole", "simvastatin", "gabapentin", "hydrochlorothiazide", "sertraline", "rosuvastatin",
    "pantoprazole", "escitalopram", "furosemide", "montelukast", "bupropion", "trazodone", "fluoxetine",
    "tamsulosin", "pravastatin", "carvedilol", "citalopram", "meloxicam", "clopidogrel", "duloxetine",
    "glipizide", "venlafaxine", "allopurinol", "warfarin", "atenolol", "famotidine", "finasteride",
    "donepezil", "spironolactone", "apixaban",
    "Eliquis", "Xarelto", "Jardiance", "Januvia", "Farxiga", "Entresto",
    "Ozempic", "Rybelsus", "Trelegy", "Linzess", "Tradjenta", "Janumet",
    "Lipitor", "Crestor", "Zoloft", "Synthroid",
)
QUANTITIES = (30,)                # tablets a month; the default, and what most people take
ROUND_EVERY = 5 * 3600            # seconds between rounds
# Prices are kept for 12 hours (http.py). Re-fetching what's past half of that,
# every five hours, means a warmed price is never older than about ten.
REFRESH_AFTER = 0.5
_WORKERS = 4                      # medicines at a time: quick, and gentle on free public APIs


@dataclass(frozen=True)
class Round:
    medicines: int                # names looked up
    priced: int                   # exact drugs (a name and a strength) now answered from the cache
    failed: tuple[str, ...]       # names a source didn't answer for; the next round tries again
    seconds: float


def cache_dir() -> Path:
    return Path(os.environ.get("FAIR_REFILL_CACHE", ROOT / "cache"))


def _warm_one(check: PriceCheck, name: str, quantities: Iterable[int]) -> int:
    priced = 0
    for drug in check.rx.search(name)[0]:
        # Everything that can be offered as a choice is warmed, the liquid as
        # well as the tablets: the follow-up ("the 20 milligram") looks the
        # choice up by ID and prices it, whichever one it is.
        check.rx.drug(drug.rxcui)
        for quantity in quantities:
            if check.check(drug, quantity).kind == "unavailable":
                raise SourceUnavailable(name)
        priced += comparable_form(drug.form)
    return priced


def warm(check: PriceCheck, medicines: Iterable[str] = MEDICINES, quantities: Iterable[int] = QUANTITIES,
         on_done: Callable[[str, int | None], None] | None = None) -> Round:
    """Look up every strength of each medicine through `check`, so its cache
    holds the answers. One medicine failing doesn't stop the rest."""
    names, quantities = list(medicines), tuple(quantities)
    started = time.perf_counter()

    def one(name: str) -> int | None:
        try:
            priced = _warm_one(check, name, quantities)
        except (SourceUnavailable, httpx.HTTPError, KeyError, ValueError):
            priced = None
        if on_done:
            on_done(name, priced)
        return priced

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        results = list(pool.map(one, names))
    return Round(medicines=len(names), priced=sum(r or 0 for r in results),
                 failed=tuple(n for n, r in zip(names, results, strict=True) if r is None),
                 seconds=time.perf_counter() - started)


def _fresh_check() -> PriceCheck:
    return PriceCheck(Http(cache_dir=cache_dir(), refresh_after=REFRESH_AFTER))


_one_at_a_time = threading.Lock()


def one_round() -> Round | None:
    """One round, now, for a caller that schedules them itself (a hosted
    server that only has CPU while answering a request). None if a round is
    already running: two at once would ask every source twice."""
    if not _one_at_a_time.acquire(blocking=False):
        return None
    try:
        return warm(_fresh_check())
    finally:
        _one_at_a_time.release()


def _keep_warm() -> None:
    while True:
        done = warm(_fresh_check())
        missed = f", {len(done.failed)} to retry" if done.failed else ""
        print(f"  Pre-warmed {done.priced} medicines in {done.seconds:.0f}s{missed}", flush=True)
        time.sleep(ROUND_EVERY)


def in_background() -> threading.Thread | None:
    """Start keeping the cache warm, unless FAIR_REFILL_PREWARM=0. The server
    answers from the first moment; early questions are just cold ones."""
    if os.environ.get("FAIR_REFILL_PREWARM", "1") == "0":
        return None
    thread = threading.Thread(target=_keep_warm, name="fair-refill-prewarm", daemon=True)
    thread.start()
    return thread


def main() -> None:
    def show(name: str, priced: int | None) -> None:
        print(f"  {name:<22} {'no answer, will retry' if priced is None else f'{priced} ready'}", flush=True)

    done = warm(_fresh_check(), on_done=show)
    print(f"\n  {done.priced} medicines across {done.medicines} names in {done.seconds:.0f}s -> {cache_dir()}")
    if done.failed:
        print(f"  No answer for: {', '.join(done.failed)}")


if __name__ == "__main__":
    main()
