"""
A simulated Alexa+ that uses Fair Refill the way Alexa+ would: as an MCP client.

    python -m fair_refill.simulator         # http://127.0.0.1:8765 — the add-on and the simulator

Alexa+'s developer tools aren't available to hackathon entrants, so this
stands in for Alexa+. It connects to the add-on's MCP endpoint over
Streamable HTTP, picks a tool from what was said (brain.py), calls it, speaks
the `speech` it gets back, and renders the add-on's own MCP App card — fetched
from the add-on with resources/read, not bundled here.

By default one process serves both, on one port. Point FAIR_REFILL_MCP_URL
elsewhere to use the simulator against an add-on running somewhere else.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from mcp import Client
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from .brain import State, route
from .server import CARD_URI, build

PAGE = (Path(__file__).parent / "simulator.html").read_text(encoding="utf-8")
HOST = os.environ.get("FAIR_REFILL_HOST", "127.0.0.1")
PORT = int(os.environ.get("FAIR_REFILL_PORT", "8765"))
MCP_URL = os.environ.get("FAIR_REFILL_MCP_URL", f"http://{HOST}:{PORT}/mcp")


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
    tool, args = route(text, state)
    started = time.perf_counter()
    if tool == "say":
        result: dict[str, Any] = {"kind": "say", "speech": args["speech"]}
    else:
        async with Client(MCP_URL) as client:
            if tool == "remove_my_medicine" and args.get("_by_name"):
                result = await _remove_by_name(client, args["_by_name"])
            else:
                result = await _call(client, tool, {k: v for k, v in args.items() if not k.startswith("_")})

    # What the conversation carries into the next turn.
    new_state = {"choices": [], "medicine": state.medicine, "you_pay": state.you_pay, "quantity": state.quantity}
    if "you_pay_per_month" in args:
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
    async with Client(MCP_URL) as client:
        resource = await client.read_resource(CARD_URI)
    return HTMLResponse(resource.contents[0].text)


async def page(_: Request) -> HTMLResponse:
    return HTMLResponse(PAGE)


def app():
    starlette = build().streamable_http_app(host=HOST)
    starlette.router.routes[0:0] = [Route("/", page), Route("/api/ask", ask, methods=["POST"]),
                                    Route("/api/card", card)]
    return starlette


def main() -> None:
    import uvicorn

    print(f"\n  Fair Refill — simulated Alexa+ at http://{HOST}:{PORT}  (add-on: {MCP_URL})\n")
    uvicorn.run(app(), host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
