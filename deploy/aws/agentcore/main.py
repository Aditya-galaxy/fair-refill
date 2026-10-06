"""
What Amazon Bedrock AgentCore Runtime starts: the Fair Refill add-on, alone.

AgentCore's contract for an MCP server is Streamable HTTP at 0.0.0.0:8000/mcp,
keeping nothing between requests (AgentCore manages sessions itself and adds
its own Mcp-Session-Id). The add-on already speaks that; these are the
settings that make it so. They are set here as well as in the Dockerfile so
the contract holds however the file is run.
"""

import os

os.environ.setdefault("FAIR_REFILL_HOST", "0.0.0.0")      # noqa: S104 - inside AgentCore's sandbox
os.environ.setdefault("FAIR_REFILL_PORT", "8000")
os.environ.setdefault("FAIR_REFILL_STATELESS", "1")
# Callers are many: a list of medicines is kept only under the key a caller
# sends in X-Fair-Refill-List (allowlisted in agentcore.sh), never shared.
os.environ.setdefault("FAIR_REFILL_PUBLIC", "1")
# A runtime session is short-lived and has its own disk, so a ten-minute
# round of pre-warming would be thrown away with it.
os.environ.setdefault("FAIR_REFILL_PREWARM", "0")

from fair_refill.server import main

if __name__ == "__main__":
    main()
