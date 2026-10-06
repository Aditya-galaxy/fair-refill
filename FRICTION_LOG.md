# Friction log

Kept as it happened, for the Amazon Developer Hackathon (Alexa+ track). Each
entry gives the task, the steps taken, what was expected, what happened, how
bad it was, the workaround, and what would fix it.

| # | Friction | Severity |
|---|---|---|
| 1 | Alexa+ developer tools are closed to hackathon entrants | High |
| 2 | Ring's API is US-only, and the Playground can't stand in for it | High for non-US entrants |
| 3 | The Alexa+ track's "Build with Agent Skills" link doesn't say how to build one | Medium |
| 4 | MCP Python SDK v2 renamed `FastMCP` to `MCPServer` | Low |

## 1. Alexa+ developer tools are closed to hackathon entrants

- **Task:** build and test an Alexa+ add-on.
- **Steps taken:**
  1. Read the Alexa+ track description and the setup pages for the Category SDK, MCP Toolkit, CLI and Web Simulator.
  2. Looked for how to get access to any of them.
  3. Read the hackathon FAQ.
- **Expected:** access to the MCP Toolkit, the CLI or the Web Simulator, since the Alexa+ track exists to build for them.
- **Actual:** the FAQ says all four are preview-only for select partners, with no way for entrants to get access. Several setup pages don't say so, which the FAQ admits "has caused some confusion".
- **Severity:** high. The platform being built for can't be tested against, so an entry can't show its add-on running on Alexa+.
- **Workaround:** a self-hosted MCP server over Streamable HTTP, plus our own web front end that stands in for Alexa+ as an MCP client (`fair_refill/simulator.py`).
- **Suggestion:** a hackathon sandbox tier for the Web Simulator, even rate-limited. At the least, put the preview-only notice at the top of every setup page, not only in the FAQ.

## 2. Ring's API is US-only, and the Playground can't stand in for it

- **Task:** decide whether the Ring track could be entered from outside the US.
- **Steps taken:**
  1. Read the Ring development guide for device and account requirements.
  2. Looked at what the Playground simulates.
  3. Read another entrant's report on the developer forum (topic 45309).
- **Expected:** either API access for a non-US account, or a Playground that covers enough of the API to build and demo against.
- **Actual:** the development guide says the API supports US-located devices only. On the forum, another entrant documented that the Playground offers one doorbell, simulated events carry no `sub_type`, chime playback can't be exercised, and sensors aren't available. The question had no answer when read.
- **Severity:** high for non-US entrants. It ruled the track out before any code was written.
- **Workaround:** entered the Alexa+ track instead.
- **Suggestion:** a Playground device set that covers the documented payloads. Failing that, a table on the track page of which features non-US entrants can demo.

## 3. The Alexa+ track's "Build with Agent Skills" link doesn't say how to build one

- **Task:** add an Agent Skill to the add-on. The rules accept "a working Agent Skill" for the Alexa+ track and list Agent Skills among examples of creative use.
- **Steps taken:**
  1. Opened the hackathon Resources page and followed the Alexa+ track's "Build with Agent Skills" link.
  2. Followed that page's link to its agent skills guide.
- **Expected:** the format of a skill (the `SKILL.md` file, its required fields, the folder layout) and what Alexa+ expects of one.
- **Actual:** the link goes to the MCP Apps documentation, to a section listing four ready-made skills that help a coding agent scaffold an MCP App (`create-mcp-app` and three others). Its guide covers installing those four. Neither page describes how to write a skill, and neither mentions Alexa+. The Resources page has one other Alexa+ link, to the Streamable HTTP transport spec.
- **Severity:** medium. The skill got written, but with no way to know whether Alexa+ expects anything beyond the open format.
- **Workaround:** wrote `skills/fair-refill/SKILL.md` to the open Agent Skills format (a `name` matching the folder, a `description`, optional `license`, `compatibility` and `metadata`), and added a test that checks those constraints and that the skill names exactly the tools the server has (`tests/test_skill.py`).
- **Suggestion:** link the Agent Skills format itself from the Resources page, and add one page saying what Alexa+ does with a skill: how it's installed, when it's loaded, and any limits on size or fields. A sample skill for an MCP add-on would do most of that.

## 4. MCP Python SDK v2 renamed `FastMCP` to `MCPServer`

- **Task:** start an MCP server from current documentation and examples.
- **Steps taken:**
  1. Installed the current `mcp` package, which is 2.x.
  2. Wrote the server with `from mcp.server.fastmcp import FastMCP`, as the examples do.
- **Expected:** the import to work.
- **Actual:** it fails on `mcp` 2.x. The error message points to the migration guide, which gives the new name: `MCPServer` in `mcp.server.mcpserver`.
- **Severity:** low. The error message is exemplary.
- **Workaround:** used `MCPServer`, and pinned `mcp>=2.2,<3` in `pyproject.toml`.
- **Suggestion:** pin hackathon starter samples to the SDK version they were written for, or note the rename beside them.
