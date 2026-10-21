"""
A simulated Alexa+ that uses Fair Refill the way Alexa+ would: as an MCP client.

    python -m fair_refill.simulator         # http://127.0.0.1:8765 — the add-on and the simulator

Alexa+'s developer tools aren't available to hackathon entrants, so this
stands in for Alexa+. It connects to the add-on's MCP endpoint over
Streamable HTTP, picks a tool from what was said (brain.py), calls it, speaks
the `speech` it gets back, and renders the add-on's own MCP App card — fetched
from the add-on with resources/read, not bundled here.

When it's hosted somewhere that only gives a process CPU while it answers a
request, the background pre-warming can't run. Set FAIR_REFILL_PREWARM_TOKEN
and have a scheduler POST /api/prewarm with that token in X-Prewarm-Token
every few hours: each call runs one round inside its own request.

By default one process serves both, on one port. Point FAIR_REFILL_MCP_URL
elsewhere to use the simulator against an add-on running somewhere else.

To put it where other people can reach it (deploy/aws), set FAIR_REFILL_HOST
to 0.0.0.0 and FAIR_REFILL_PUBLIC=1. Each browser then keeps its own list of
medicines, under a key it makes up and sends along (cabinet.py), and
FAIR_REFILL_STATELESS=1 lets any copy of the server answer any request.
"""

from __future__ import annotations

import hmac
import os
import re
import time
from pathlib import Path
from typing import Any

from mcp import Client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route

from . import prewarm
from .brain import State, route
from .cabinet import LIST_HEADER
from .server import CARD_URI, build

PAGE = (Path(__file__).parent / "simulator.html").read_text(encoding="utf-8")
HOST = os.environ.get("FAIR_REFILL_HOST", "127.0.0.1")
PORT = int(os.environ.get("FAIR_REFILL_PORT", "8765"))
# Listening on every address isn't an address to call: reach ourselves on loopback.
_SELF = "127.0.0.1" if HOST in ("0.0.0.0", "::") else HOST     # noqa: S104
MCP_URL = os.environ.get("FAIR_REFILL_MCP_URL", f"http://{_SELF}:{PORT}/mcp")
STATELESS = os.environ.get("FAIR_REFILL_STATELESS", "0") == "1"


def _client(list_key: str | None = None) -> Client:
    """A connection to the add-on, saying whose list of medicines it's for."""
    if not list_key:
        return Client(MCP_URL)
    return Client(streamable_http_client(MCP_URL, http_client=create_mcp_http_client({LIST_HEADER: list_key})))


async def _call(client: Client, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    result = await client.call_tool(tool, args)
    data = result.structured_content
    if data is None:
        import json
        data = json.loads(result.content[0].text)
    return data.get("result", data) if isinstance(data, dict) and set(data) == {"result"} else data


async def _remove_by_name(client: Client, name: str) -> dict[str, Any]:
    """"Remove my lisinopril": find it on the list first, as Alexa+ would chain the two tools."""
    listed = await _call(client, "list_my_medicines", {})
    words = [w for w in re.findall(r"[a-z]+", name.lower()) if len(w) > 3]
    matches = [m for m in listed.get("medicines", []) if any(w in m["name"].lower() for w in words)]
    if len(matches) != 1:
        return {"kind": "not_found", "speech": "Which medicine should I take off your list? Say its name as it's "
                                               "on the list."}
    return await _call(client, "remove_my_medicine", {"choice_id": matches[0]["choice_id"]})


async def ask(request: Request) -> JSONResponse:
    body = await request.json()
    text = str(body.get("text", ""))[:500]
    state = State.from_dict(body.get("state"))
    list_key = str(body.get("list") or "")[:64] or None
    chosen = str(body.get("choice_id") or "")
    picked = next((c for c in state.choices if c.get("choice_id") == chosen), None) if chosen else None
    if picked:
        # Tapped on the card: the option is known exactly, no words to interpret.
        tool, args = "check_chosen_medicine", {"choice_id": picked["choice_id"], "monthly_quantity": state.quantity}
        if state.you_pay is not None:
            args["you_pay_per_month"] = state.you_pay
    else:
        tool, args = route(text, state)
    started = time.perf_counter()
    if tool == "say":
        result: dict[str, Any] = {"kind": "say", "speech": args["speech"]}
    else:
        async with _client(list_key) as client:
            if tool == "remove_my_medicine" and args.get("_by_name"):
                result = await _remove_by_name(client, args["_by_name"])
            else:
                result = await _call(client, tool, {k: v for k, v in args.items() if not k.startswith("_")})

    # What the conversation carries into the next turn.
    new_state = {"choices": [], "medicine": state.medicine, "you_pay": state.you_pay, "quantity": state.quantity}
    if tool == "check_prescription_price":
        # What someone pays belongs to the medicine they said it about: "$40"
        # for atorvastatin says nothing about their metformin.
        new_state["you_pay"] = args.get("you_pay_per_month")
    elif "you_pay_per_month" in args:
        new_state["you_pay"] = args["you_pay_per_month"]
    if "monthly_quantity" in args:
        new_state["quantity"] = args["monthly_quantity"]
    if result.get("kind") == "choose":
        new_state["choices"] = result.get("choices", [])
    if result.get("medicine"):
        new_state["medicine"] = result["medicine"]

    return JSONResponse({"speech": result.get("speech", ""), "kind": result.get("kind"), "card": result.get("card"),
                         "result": result, "tool": tool if tool != "say" else None,
                         "arguments": {k: v for k, v in args.items() if not k.startswith("_")},
                         "ms": round((time.perf_counter() - started) * 1000), "state": new_state})


async def card(_: Request) -> HTMLResponse:
    """The add-on's own card, read from it over MCP (resources/read)."""
    async with _client() as client:
        resource = await client.read_resource(CARD_URI)
    return HTMLResponse(resource.contents[0].text)


async def page(_: Request) -> HTMLResponse:
    return HTMLResponse(PAGE)


async def health(_: Request) -> PlainTextResponse:
    """For a load balancer: the process is up. It answers before the first
    pre-warm round has finished; early questions are just slower."""
    return PlainTextResponse("ok")


async def prewarm_now(request: Request) -> JSONResponse:
    """One pre-warm round, for a scheduler. Only with the token it was given:
    a round asks the public price sources a few thousand questions, so it is
    not something anyone on the internet should be able to start."""
    token = os.environ.get("FAIR_REFILL_PREWARM_TOKEN", "")
    if not token:
        return JSONResponse({"error": "not found"}, status_code=404)
    if not hmac.compare_digest(request.headers.get("x-prewarm-token", ""), token):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    done = await run_in_threadpool(prewarm.one_round)
    if done is None:
        return JSONResponse({"error": "a round is already running"}, status_code=409)
    return JSONResponse({"medicines": done.medicines, "priced": done.priced, "failed": list(done.failed),
                         "seconds": round(done.seconds)})


def app():
    starlette = build().streamable_http_app(host=HOST, stateless_http=STATELESS)
    starlette.router.routes[0:0] = [Route("/", page), Route("/api/ask", ask, methods=["POST"]),
                                    Route("/api/card", card), Route("/health", health),
                                    Route("/api/prewarm", prewarm_now, methods=["POST"])]
    return starlette


def main() -> None:
    import uvicorn

    print(f"\n  Fair Refill — simulated Alexa+ at http://{HOST}:{PORT}  (add-on: {MCP_URL})\n")
    served = app()
    prewarm.in_background()
    uvicorn.run(served, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
