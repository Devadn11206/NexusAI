import sys
from pathlib import Path
import pytest
from app.tools.mcp import MCPClientManager


@pytest.mark.asyncio
async def test_mcp_registration_and_tool_discovery():
    mgr = MCPClientManager()
    mock_server_script = str(Path(__file__).parent / "mock_mcp_server.py")

    # Register the mock MCP server
    mgr.register_server(
        name="math_service",
        command=sys.executable,
        args=[mock_server_script],
    )

    assert "math_service" in mgr.list_registered_servers()

    # Discover tools
    tools = await mgr.list_tools("math_service")
    assert len(tools) >= 2
    tool_names = [t["name"] for t in tools]
    assert "calculate_sum" in tool_names
    assert "echo_uppercase" in tool_names


@pytest.mark.asyncio
async def test_mcp_tool_execution():
    mgr = MCPClientManager()
    mock_server_script = str(Path(__file__).parent / "mock_mcp_server.py")

    mgr.register_server(
        name="math_service",
        command=sys.executable,
        args=[mock_server_script],
    )

    # 1. Execute calculate_sum tool
    res_sum = await mgr.call_tool(
        tool_name="calculate_sum",
        arguments={"a": 42, "b": 58},
        server_name="math_service",
    )

    assert res_sum["status"] == "success"
    assert "100" in res_sum["content"]

    # 2. Execute echo_uppercase tool
    res_echo = await mgr.call_tool(
        tool_name="echo_uppercase",
        arguments={"text": "hello from nexus ai"},
        server_name="math_service",
    )

    assert res_echo["status"] == "success"
    assert "HELLO FROM NEXUS AI" in res_echo["content"]


@pytest.mark.asyncio
async def test_mcp_nonexistent_tool():
    mgr = MCPClientManager()
    res = await mgr.call_tool("nonexistent_tool", {})
    assert res["status"] == "failed"
    assert "No registered MCP server found" in res["error"]

