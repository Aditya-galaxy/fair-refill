"""
Record real API responses for the tests.

    python tools/record_fixtures.py                  # every scenario, from scratch
    python tools/record_fixtures.py "Ozempic"        # only these, added to the file

Runs each scenario through the real pipeline against the live APIs, with no
cache, and saves every request and response to tests/fixtures/responses.json.
The tests replay exactly these, so they test behaviour on real data without
ever going online. Re-record when a source changes shape — and look at the
diff: a price moving is expected, a field disappearing is not.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fair_refill.http import USER_AGENT, Http, RecordingTransport  # noqa: E402
from fair_refill.service import PriceCheck  # noqa: E402

SCENARIOS = [
    ("atorvastatin 20 mg", None),
    ("atorvastatin 20 mg", 40.0),
    ("Lipitor 20", None),
    ("lipiter 20", None),
    ("eliquis 5 mg", None),
    ("metformin 500", None),
    ("metformin 500 mg extended release", None),
    ("albuterol inhaler", None),
    ("lisinopril 10 mg", 15.0),
    ("atorvastatin", None),
    ("xyzzy", None),
    ("Ozempic", None),
    ("Tradjenta", None),
    ("Linzess 145 mcg", None),
    ("Enbrel", None),
    ("levothyroxine 50 mcg", None),
    ("metoprolol tartrate 25 mg", 20.0),
    ("pantoprazole 40 mg", None),
    ("omeprazole 20 mg", None),
]


def main() -> int:
    out = ROOT / "tests" / "fixtures" / "responses.json"
    only = set(sys.argv[1:])
    # Naming scenarios adds to what's recorded: requests already in the file
    # are answered from it, so one new medicine doesn't move every other
    # test's prices to a new week.
    transport = RecordingTransport(json.loads(out.read_text(encoding="utf-8")) if only else None)
    http = Http(httpx.Client(transport=transport, headers={"User-Agent": USER_AGENT}, timeout=40))
    check = PriceCheck(http)
    for text, you_pay in [s for s in SCENARIOS if not only or s[0] in only]:
        result = check.ask(text, you_pay=you_pay)
        print(f"  {text!r:<40} {result.kind:<10} {result.speech[:90]}")
        # The MCP tools refer back to drugs by ID ("the regular tablet"), so
        # record looking each one up and pricing it, as a follow-up would.
        for drug in result.choices:
            again = check.rx.drug(drug.rxcui)
            if again and result.kind == "choose":
                follow = check.check(again, 30, you_pay)
                print(f"    ↳ {again.spoken:<36} {follow.kind:<10} {follow.speech[:70]}")
    out.write_text(json.dumps(transport.recorded, indent=1, sort_keys=True), encoding="utf-8")
    print(f"\n  {transport.fetched} fetched, {len(transport.recorded)} responses in {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
