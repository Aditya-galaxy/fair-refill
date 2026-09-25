"""
Record real API responses for the tests.

    python tools/record_fixtures.py

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
]


def main() -> int:
    transport = RecordingTransport()
    http = Http(httpx.Client(transport=transport, headers={"User-Agent": USER_AGENT}, timeout=40))
    check = PriceCheck(http)
    for text, you_pay in SCENARIOS:
        result = check.ask(text, you_pay=you_pay)
        print(f"  {text!r:<40} {result.kind:<10} {result.speech[:90]}")
    out = ROOT / "tests" / "fixtures" / "responses.json"
    out.write_text(json.dumps(transport.recorded, indent=1, sort_keys=True), encoding="utf-8")
    print(f"\n  {len(transport.recorded)} responses -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
