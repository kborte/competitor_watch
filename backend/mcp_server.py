"""Minimal MCP server exposing one tool: submit_findings.

Why this exists: the Claude Routine's sandbox blocks outbound network
connections it initiates itself (curl, WebFetch both hit the same
egress denial). MCP tool calls are a different mechanism — the routine
declares this server in its config and Anthropic's own infrastructure is
what connects to it, not the sandbox. Unproven until tested against a real
routine; this file is the thing to point the routine's mcp_servers config
at once it's reachable from outside this machine.

Run locally:
    WEBHOOK_SECRET=... python3 -m backend.mcp_server
"""

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from . import config
from . import ingest as ingest_logic
from .schemas import IngestPayload

mcp = MCPServer("competitor-watch-ingest")

# The SDK's DNS-rebinding protection rejects any Host header other than what's
# in this allowlist — which includes a tunnel/public hostname, not just
# 127.0.0.1. Update MCP_PUBLIC_HOST in .env whenever the public URL changes
# (e.g. a new cloudflared quick tunnel).
_TRANSPORT_SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1:8200", "localhost:8200"] + (
        [config.MCP_PUBLIC_HOST] if config.MCP_PUBLIC_HOST else []
    ),
)


@mcp.tool()
def submit_findings(secret: str, payload: IngestPayload) -> dict:
    """Submit a batch of competitor-watch findings for ingestion.
    `secret` must match the configured webhook secret."""
    if secret != config.WEBHOOK_SECRET:
        return {"status": "error", "detail": "bad secret"}
    return ingest_logic.process(payload)


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http", host="127.0.0.1", port=8200,
        transport_security=_TRANSPORT_SECURITY,
    )
