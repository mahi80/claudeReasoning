"""Tiny MCP server used by the tests (stdio transport)."""
from mcp.server.mcpserver import MCPServer

server = MCPServer("demo")


@server.tool()
def add(a: int, b: int) -> str:
    """Add two integers and return the sum."""
    return str(a + b)


if __name__ == "__main__":
    server.run()
