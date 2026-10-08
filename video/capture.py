"""
Photograph the product, one moment at a time.

    python -m fair_refill.simulator          # in another terminal (FAIR_REFILL_PORT=8791)
    python video/capture.py

For every question in video/script.json this takes two frames of the simulated
Alexa+ page: the question just heard, and the add-on's answer with its card.
Each frame is the real page in a real (headless) browser, loaded from a link
that carries the conversation so far (`/?ask=…&ask=…`), so what is filmed is
what the add-on answered that day and nothing typed in afterwards. The answers
are saved to video/out/answers.json: that file is what the assistant's voice
reads, so the film can't say something the add-on didn't.

Needs Google Chrome and `pip install -e ".[video]"`.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
from websockets.sync.client import connect

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
FRAMES = OUT / "frames"
SITE = os.environ.get("FAIR_REFILL_FILM_URL", "http://127.0.0.1:8791")
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PAGE = (1600, 900, 1.2)        # the simulator: room for a whole answer under the screen
CARD = (1280, 720, 1.5)        # title cards: larger type. Both come out 1920 x 1080.
DEBUG_PORT = 9377


class Browser:
    """Headless Chrome, driven over its DevTools protocol."""

    def __init__(self) -> None:
        self.profile = tempfile.mkdtemp(prefix="fair-refill-film-")
        self.process = subprocess.Popen(
            [CHROME, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}", f"--user-data-dir={self.profile}",
             "--hide-scrollbars", "--mute-audio", "--no-first-run", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        target = None
        for _ in range(100):
            try:
                pages = httpx.get(f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=2).json()
                target = next(p for p in pages if p["type"] == "page")
                break
            except (httpx.HTTPError, StopIteration):
                time.sleep(0.1)
        if target is None:
            raise RuntimeError("Chrome didn't start")
        self.ws = connect(target["webSocketDebuggerUrl"], max_size=None).__enter__()
        self.n = 0
        self.send("Page.enable")

    def send(self, method: str, params: dict | None = None) -> dict:
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == self.n:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message["result"]

    def value(self, expression: str) -> object:
        return self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})["result"].get("value")

    def shoot(self, url: str, ready: str, name: str, view: tuple[int, int, float] = PAGE,
              settle: float = 0.7) -> Path:
        self.send("Emulation.setDeviceMetricsOverride",
                  {"width": view[0], "height": view[1], "deviceScaleFactor": view[2], "mobile": False})
        self.send("Page.navigate", {"url": url})
        deadline = time.monotonic() + 90
        while self.value(ready) is not True:
            if time.monotonic() > deadline:
                raise RuntimeError(f"the page never got to {ready!r}: {url}")
            time.sleep(0.15)
        time.sleep(settle)                          # the card paints after its message arrives
        png = base64.b64decode(self.send("Page.captureScreenshot", {"format": "png"})["data"])
        path = FRAMES / f"{name}.png"
        path.write_bytes(png)
        return path

    def close(self) -> None:
        self.ws.__exit__(None, None, None)
        self.process.terminate()
        self.process.wait(timeout=10)
        shutil.rmtree(self.profile, ignore_errors=True)


def main() -> int:
    script = json.loads((HERE / "script.json").read_text(encoding="utf-8"))
    try:
        httpx.get(f"{SITE}/health", timeout=5).raise_for_status()
    except httpx.HTTPError:
        print(f"Start the simulator first: FAIR_REFILL_PORT={SITE.rsplit(':', 1)[-1]} python -m fair_refill.simulator")
        return 1
    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)

    # Ask everything once first, in order, so the page's replay is instant and
    # the frames don't catch "One moment…".
    answers: dict[str, dict] = {}
    state = None
    for seg in script["segments"]:
        if seg["kind"] != "turn":
            continue
        r = httpx.post(f"{SITE}/api/ask", timeout=120,
                       json={"text": seg["ask"], "state": state, "list": "film-rehearsal-" + "0" * 34}).json()
        state = r["state"]
        answers[seg["id"]] = {"ask": seg["ask"], "speech": r["speech"], "tool": r["tool"], "kind": r["kind"]}
        print(f"  {seg['id']:<13} {r['kind']:<10} {r['speech'][:70]}")

    done = "document.body.dataset.asked === 'done'"
    loaded = "document.readyState === 'complete'"
    browser = Browser()
    try:
        asked: list[str] = []
        for seg in script["segments"]:
            if seg["kind"] == "card":
                browser.shoot((HERE / "cards" / seg["card"]).as_uri(), loaded, seg["id"], view=CARD, settle=0.3)
                continue
            heard = urlencode([("ask", q) for q in asked] + [("hear", seg["ask"])])
            browser.shoot(f"{SITE}/?{heard}", done, f"{seg['id']}-heard")
            asked.append(seg["ask"])
            browser.shoot(f"{SITE}/?{urlencode([('ask', q) for q in asked])}", done, f"{seg['id']}-answered")
            # The page's own answer must be the one the voice will read.
            on_page = browser.value("document.getElementById('alexa').textContent")
            if on_page != answers[seg["id"]]["speech"]:
                raise RuntimeError(f"{seg['id']}: the page shows a different answer from the one recorded")
    finally:
        browser.close()

    (OUT / "answers.json").write_text(json.dumps(answers, indent=1), encoding="utf-8")
    print(f"\n  {len(list(FRAMES.glob('*.png')))} frames in {FRAMES.relative_to(HERE.parent)}, "
          "answers in video/out/answers.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
