"""
The Agent Skill, held to the Agent Skills format and to the add-on it
describes: it names every tool the server has and none it doesn't, and the
server hands it out.
"""

from __future__ import annotations

import asyncio
import re

from mcp import Client

from fair_refill.compare import CASH_CAVEAT
from fair_refill.server import SKILL_PATH, SKILL_URI, build

SKILL_DIR = SKILL_PATH.parent
TEXT = SKILL_PATH.read_text(encoding="utf-8")
_, FRONT, BODY = TEXT.split("---\n", 2)


def _front(key: str) -> str:
    return re.search(rf"^{key}: (.+)$", FRONT, flags=re.MULTILINE).group(1)


def test_frontmatter_meets_the_agent_skills_format():
    name = _front("name")
    assert name == SKILL_DIR.name                                   # the name is the folder's name
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) and len(name) <= 64
    assert 1 <= len(_front("description")) <= 1024
    assert len(_front("compatibility")) <= 500
    assert _front("license") == "Apache-2.0"
    assert len(BODY.splitlines()) < 500                             # the format's guidance for the main file


def test_every_file_it_points_to_exists():
    links = re.findall(r"\]\((references/[^)]+)\)", BODY)
    assert links
    for link in links:
        assert (SKILL_DIR / link).is_file(), link


def _server_side():
    async def go():
        async with Client(build(), raise_exceptions=True) as client:
            tools = {t.name for t in (await client.list_tools()).tools}
            served = (await client.read_resource(SKILL_URI)).contents[0].text
            return tools, served
    return asyncio.run(go())


def test_it_names_exactly_the_tools_the_server_has(tmp_path, monkeypatch):
    monkeypatch.setenv("FAIR_REFILL_STATE", str(tmp_path))
    monkeypatch.setenv("FAIR_REFILL_CACHE", str(tmp_path))
    tools, served = _server_side()
    table = BODY.split("## Tools")[1].split("## ")[0]
    assert set(re.findall(r"^\| `(\w+)` \|", table, flags=re.MULTILINE)) == tools
    assert served == TEXT                                           # the add-on serves the skill as it is in the repo


def test_it_carries_the_rules_the_answers_keep():
    for rule in ("identical drug only", "Never add a price of your own", "Keep the last sentence",
                 "Keep the catch with the cash price"):
        assert rule in BODY, rule
    # The skill names the same catch the add-on says aloud.
    assert "Medicare's yearly limit" in BODY and "Medicare's yearly limit" in CASH_CAVEAT
