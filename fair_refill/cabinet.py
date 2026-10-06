"""
"My medicines": the list someone asks Fair Refill to remember.

A list of prescriptions is health information, so it stays on the machine
running the add-on, in one JSON file, and every entry can be removed by voice.
Nothing is sent anywhere except the medicine's name and strength, to the
public price sources, when it's checked.

On someone's own machine there is one list. A server that many people reach
(`Cabinets(public=True)`) must never hand one person another's medicines, so
there each list is kept under a long random key the client chooses and sends
with every request, and a request without one gets no list at all. The key
is a secret between that client and the server, like a session cookie; it
isn't an identity. On Alexa+ the account would take its place.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Saved:
    choice_id: str               # RxNorm ID of the exact drug
    name: str                    # as said aloud
    monthly_quantity: int
    you_pay_per_month: float | None


class Cabinet:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def all(self) -> list[Saved]:
        if not self.path.exists():
            return []
        return [Saved(**d) for d in json.loads(self.path.read_text(encoding="utf-8"))]

    def _save(self, items: list[Saved]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".cabinet-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump([asdict(i) for i in items], fh, indent=1)
        os.replace(tmp, self.path)

    def add(self, item: Saved) -> None:
        with self._lock:
            self._save([i for i in self.all() if i.choice_id != item.choice_id] + [item])

    def remove(self, choice_id: str) -> Saved | None:
        with self._lock:
            items = self.all()
            gone = next((i for i in items if i.choice_id == choice_id), None)
            if gone:
                self._save([i for i in items if i.choice_id != choice_id])
            return gone


LIST_HEADER = "x-fair-refill-list"
_LIST_KEY = re.compile(r"[A-Za-z0-9_-]{20,64}")      # long enough not to be guessed


class Cabinets:
    """Whose list a request means."""

    def __init__(self, state: Path, public: bool = False, own: Cabinet | None = None) -> None:
        self.state = state
        self.public = public
        self.own = own or Cabinet(state / "my_medicines.json")

    def of(self, key: str | None) -> Cabinet | None:
        """The list kept under `key`. With no usable key: the machine's own
        list, or on a public server none."""
        if key and _LIST_KEY.fullmatch(key):
            return Cabinet(self.state / "lists" / f"{key}.json")
        return None if self.public else self.own
