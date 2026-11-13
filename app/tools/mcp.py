import asyncio
import json
import logging
import os
import sys
from typing import Dict, Any, List, Optional
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class MCPClientManager:
    """
    Model Context Protocol (MCP) Integration Manager for NEXUS AI.
    Allows registering, connecting, discovering, and executing tools from external
    stdio-based or network-based MCP servers (e.g. SQLite, GitHub, Google Drive, Filesystem).
    """

    def __init__(self):
        self.server_configs: Dict[str, Dict[str, Any]] = {}
        self._discovered_tools: Dict[str, Dict[str, Any]] = {}

    def register_server(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> None:
        """Register an MCP server configuration."""
        clean_name = name.strip().lower()
        self.server_configs[clean_name] = {
            "name": clean_name,
            "command": command,
            "args": args or [],
            "env": env or {},
            "cwd": cwd,
        }
        logger.info(f"[MCPManager] Registered MCP server: '{clean_name}' (cmd={command})")

    def unregister_server(self, name: str) -> bool:
        clean_name = name.strip().lower()
        if clean_name in self.server_configs:
            del self.server_configs[clean_name]
            return True
        return False

    def list_registered_servers(self) -> List[str]:
        return list(self.server_configs.keys())

    async def list_tools(self, server_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Connects to registered MCP server(s) and discovers available tools and their input schemas.
        """
        targets = [server_name.lower()] if server_name else list(self.server_configs.keys())
        all_tools = []

        for s_name in targets:
            config = self.server_configs.get(s_name)
            if not config:
                continue

            try:
                server_env = os.environ.copy()
                server_env.update(config.get("env", {}))

                server_params = StdioServerParameters(
                    command=config["command"],
                    args=config["args"],
                    env=server_env,
                )

                async with stdio_client(server_params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools_response = await session.list_tools()
                        for t in tools_response.tools:
                            tool_info = {
                                "server": s_name,
                                "name": t.name,
                                "description": t.description or "",
                                "input_schema": t.inputSchema if hasattr(t, "inputSchema") else {},
                            }
                            all_tools.append(tool_info)
                            self._discovered_tools[t.name] = tool_info
            except Exception as exc:
                logger.error(f"[MCPManager] Failed to list tools from server '{s_name}': {exc}")

        return all_tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        server_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Invokes an MCP tool on the target server and returns the structured results.
        """
        # Resolve target server
        target_server = server_name.lower() if server_name else None
        if not target_server and tool_name in self._discovered_tools:
            target_server = self._discovered_tools[tool_name].get("server")

        if not target_server:
            # If not discovered yet, try to find which server owns it
            for s_name in self.server_configs:
                tools = await self.list_tools(s_name)
                if any(t["name"] == tool_name for t in tools):
                    target_server = s_name
                    break

        if not target_server or target_server not in self.server_configs:
            return {
                "status": "failed",
                "tool": tool_name,
                "error": f"No registered MCP server found for tool '{tool_name}'",
            }

        config = self.server_configs[target_server]
        try:
            server_env = os.environ.copy()
            server_env.update(config.get("env", {}))

            server_params = StdioServerParameters(
                command=config["command"],
                args=config["args"],
                env=server_env,
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        name=tool_name,
                        arguments=arguments or {},
                    )

                    content_list = []
                    for c in getattr(result, "content", []):
                        if hasattr(c, "text"):
                            content_list.append(c.text)
                        elif hasattr(c, "data"):
                            content_list.append(str(c.data))
                        else:
                            content_list.append(str(c))

                    combined_text = "\n".join(content_list)
                    is_err = getattr(result, "isError", False)

                    return {
                        "status": "failed" if is_err else "success",
                        "server": target_server,
                        "tool": tool_name,
                        "arguments": arguments,
                        "content": combined_text,
                        "raw_content": content_list,
                    }

        except Exception as exc:
            logger.error(f"[MCPManager] Tool call error for '{tool_name}': {exc}", exc_info=True)
            return {
                "status": "failed",
                "server": target_server,
                "tool": tool_name,
                "error": str(exc),
            }


# Global Singleton Manager
mcp_manager = MCPClientManager()

