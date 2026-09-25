# Friction log

Kept as it happened, for the Amazon Developer Hackathon feedback. Each entry:
what I tried, what I expected, what happened, how bad it was, the workaround,
and what would fix it.

## 1. Alexa+ developer tools are closed to hackathon entrants
- **Task:** build and test an Alexa+ add-on.
- **Expected:** the Alexa+ MCP Toolkit, CLI or Web Simulator, since the Alexa+ track exists to build for them.
- **Happened:** the FAQ says the Category SDK, MCP Toolkit, CLI and Web Simulator are preview-only for select partners, with no way for entrants to get access. Several setup pages don't say so, which the FAQ admits "has caused some confusion".
- **Severity:** high. The platform you're building for can't be tested against.
- **Workaround:** a self-hosted MCP server (Streamable HTTP) plus our own web front end simulating Alexa+.
- **Suggestion:** a hackathon sandbox tier for the Web Simulator, even rate-limited. At minimum, put the preview-only notice on every setup page.

## 2. Ring's API is US-only, and the Playground can't stand in for it
- **Task:** evaluate the Ring track from outside the US.
- **Happened:** the development guide says the API supports US-located devices only. Another entrant documented that the Playground offers one doorbell, simulated events carry no `sub_type`, chime playback can't be exercised, and sensors aren't available (forum topic 45309, answer pending).
- **Severity:** high for non-US entrants. It decided our track choice.
- **Workaround:** chose Alexa+ instead.
- **Suggestion:** a Playground device set that covers the payloads, or say up front which track features non-US entrants can demo.

## 3. MCP Python SDK v2 renamed FastMCP to MCPServer
- **Task:** start an MCP server from the current docs and examples.
- **Happened:** `from mcp.server.fastmcp import FastMCP` fails on `mcp` 2.x. The error message helpfully points to the migration guide (`MCPServer` in `mcp.server.mcpserver`).
- **Severity:** low. The error message is exemplary.
- **Suggestion:** hackathon starter samples pinned to the SDK version they were written for.
