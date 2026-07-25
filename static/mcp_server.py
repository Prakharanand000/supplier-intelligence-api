"""Argus MCP server.

Exposes the Argus investigate_supplier endpoint as an MCP tool so any
MCP-compatible agent (Claude Code, Codex, and others) can screen an entity and
receive the full evidence-backed intelligence object.

Run it:
    pip install "mcp[cli]" httpx
    ARGUS_URL=https://your-argus-host python mcp_server.py

Then register it with your agent (see the "API & MCP" tab in the Argus UI).
"""

from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

ARGUS_URL = os.environ.get(
    "ARGUS_URL", "https://supplier-intelligence-api-1062146216736.us-central1.run.app"
).rstrip("/")

mcp = FastMCP("argus")


@mcp.tool()
async def investigate_supplier(
    name: str,
    country: str = "",
    entity_type: str = "organization",
    date_of_birth: str = "",
) -> dict:
    """Investigate a supplier, company, or person for third-party risk.

    Screens the subject against OFAC sanctions, SEC EDGAR, GLEIF, GDELT adverse
    media, and CourtListener litigation, then returns one evidence-backed JSON
    object: resolved identity, sanctions result, tagged adverse media, ownership
    graph, and an explainable risk score with a recommendation.

    Args:
        name: Legal name of the company or full name of the person (required).
        country: Country, to sharpen entity resolution.
        entity_type: "organization" or "individual".
        date_of_birth: For individuals, to confirm or rule out an OFAC name hit.
    """
    payload = {"name": name, "entity_type": entity_type}
    if country:
        payload["country"] = country
    if date_of_birth:
        payload["date_of_birth"] = date_of_birth

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ARGUS_URL}/api/v1/supplier/investigate", json=payload, timeout=180
        )
        resp.raise_for_status()
        return resp.json()


if __name__ == "__main__":
    mcp.run()
