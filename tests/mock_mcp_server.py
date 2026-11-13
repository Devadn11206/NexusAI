import asyncio
from mcp.server.mcpserver import MCPServer

server = MCPServer(name="nexus-mock-mcp")


@server.tool(name="calculate_sum", description="Add two integers together")
def calculate_sum(a: int, b: int) -> int:
    return a + b


@server.tool(name="echo_uppercase", description="Converts input text to uppercase")
def echo_uppercase(text: str) -> str:
    return text.upper()


if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())

