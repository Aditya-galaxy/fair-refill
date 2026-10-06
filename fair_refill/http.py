"""
One way to fetch JSON, so every source shares timeouts, retries and — for the
tests — a single record/replay format.

The tests never touch the network. They replay responses recorded from the
real APIs by tools/record_fixtures.py, matched by `request_key`, which both
sides compute from the httpx.Request itself. A request the recording doesn't
have fails loudly instead of quietly going online.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

import httpx

USER_AGENT = "fair-refill/0.1 (+https://github.com/Aditya-galaxy/fair-refill)"
TIMEOUT = httpx.Timeout(20.0, connect=8.0)


class SourceUnavailable(RuntimeError):
    """A price source didn't answer. Callers say so rather than guess."""


def request_key(request: httpx.Request) -> str:
    body = request.content or b""
    material = f"{request.method} {request.url} {hashlib.sha256(body).hexdigest()}"
    return hashlib.sha256(material.encode()).hexdigest()[:24]


# How long an answer from each source stays good. Drug naming (RxNorm) barely
# changes; prices are refreshed within a day, so an answer is never more than a
# day behind the source it quotes.
_TTL_SECONDS = {"rxnav.nlm.nih.gov": 7 * 86400}
_DEFAULT_TTL = 12 * 3600


class Http:
    def __init__(self, client: httpx.Client | None = None, cache_dir: Path | None = None,
                 refresh_after: float = 1.0) -> None:
        self.client = client or httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT},
                                             follow_redirects=True)
        self.cache_dir = cache_dir
        # The share of an answer's life after which it's fetched again. Someone
        # asking gets any answer that's still good (1.0); pre-warming re-fetches
        # early (prewarm.py), so nothing it keeps warm runs out between rounds.
        self.refresh_after = refresh_after

    def _cached(self, request: httpx.Request) -> Any | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / f"{request_key(request)}.json"
        if not path.exists():
            return None
        entry = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - entry["at"] > _TTL_SECONDS.get(request.url.host, _DEFAULT_TTL) * self.refresh_after:
            return None
        return entry["json"]

    def _store(self, request: httpx.Request, data: Any) -> None:
        if self.cache_dir is None:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # A name of its own per writer: parallel lookups often fetch the same
        # thing at once, and each must be able to finish its own write.
        tmp = self.cache_dir / f".{request_key(request)}.{threading.get_ident()}.tmp"
        tmp.write_text(json.dumps({"at": time.time(), "json": data}), encoding="utf-8")
        tmp.replace(self.cache_dir / f"{request_key(request)}.json")

    def _send(self, request: httpx.Request) -> Any:
        hit = self._cached(request)
        if hit is not None:
            return hit
        data = self._fetch(request)
        self._store(request, data)
        return data

    def _fetch(self, request: httpx.Request) -> Any:
        last: Exception | None = None
        for _ in range(2):                    # one retry: public APIs blip
            try:
                response = self.client.send(request)
                if response.status_code >= 500:
                    last = SourceUnavailable(f"{request.url.host} answered {response.status_code}")
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = exc
        raise SourceUnavailable(f"{request.url.host} didn't answer") from last

    def get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        return self._send(self.client.build_request("GET", url, params=params))

    def post(self, url: str, body: dict[str, Any]) -> Any:
        return self._send(self.client.build_request("POST", url, json=body))


# ── record / replay ──────────────────────────────────────────────────────────

class ReplayTransport(httpx.BaseTransport):
    def __init__(self, path: Path) -> None:
        self.recorded: dict[str, dict] = json.loads(path.read_text(encoding="utf-8"))

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        key = request_key(request)
        if key not in self.recorded:
            raise AssertionError(f"no recorded response for {request.method} {request.url} (key {key}); "
                                 f"re-run tools/record_fixtures.py")
        hit = self.recorded[key]
        return httpx.Response(hit["status"], json=hit["json"], request=request)


class RecordingTransport(httpx.BaseTransport):
    def __init__(self) -> None:
        self.inner = httpx.HTTPTransport(retries=1)
        self.recorded: dict[str, dict] = {}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self.inner.handle_request(request)
        response.read()
        self.recorded[request_key(request)] = {"url": str(request.url), "status": response.status_code,
                                               "json": response.json()}
        # The body is already decoded; passing the original Content-Encoding
        # along would make httpx decompress it a second time.
        return httpx.Response(response.status_code, content=response.content,
                              headers={"content-type": "application/json"}, request=request)


def replay_client(path: Path) -> Http:
    return Http(httpx.Client(transport=ReplayTransport(path), headers={"User-Agent": USER_AGENT}))
