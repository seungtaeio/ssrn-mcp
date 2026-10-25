"""Exercise the public MCP interface without fetching third-party content."""

import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters


EXPECTED_TOOLS = {
    "search_papers",
    "get_paper_by_doi",
    "find_open_access_link",
    "get_ssrn_reference_link",
    "make_quant_research_checklist",
    "source_and_rights_policy",
}


@pytest.mark.asyncio
async def test_mcp_tool_registration():
    from quant_paper_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.list_tools()
    names = {tool.name for tool in result.tools}
    assert names == EXPECTED_TOOLS


@pytest.mark.asyncio
async def test_stdio_initialize_list_and_call():
    """Catch broken module entry points, stdio framing, and tool dispatch."""
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "quant_paper_mcp"],
        cwd=Path(__file__).resolve().parents[1],
    )
    async with asyncio.timeout(20):
        # Force the initialize handshake used by existing desktop MCP clients.
        async with Client(server, mode="legacy", read_timeout_seconds=5) as client:
            assert client.server_info is not None
            assert client.server_info.name == "SSRN MCP (unofficial)"
            listed = await client.list_tools()
            assert {tool.name for tool in listed.tools} == EXPECTED_TOOLS

            reference = await client.call_tool(
                "get_ssrn_reference_link", {"abstract_id": "1234567"}
            )
            assert not reference.is_error
            assert json.loads(reference.content[0].text)["url"] == (
                "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1234567"
            )

            rejected = await client.call_tool(
                "get_ssrn_reference_link", {"abstract_id": "../123"}
            )
            assert rejected.is_error

            policy = await client.call_tool("source_and_rights_policy")
            assert not policy.is_error
            assert json.loads(policy.content[0].text)["used_api_origins"] == [
                "https://api.openalex.org",
                "https://api.crossref.org",
            ]
