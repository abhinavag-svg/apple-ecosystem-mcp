from __future__ import annotations

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .bridge import run_applescript

# FastMCP servers use STDIO transport by default when `run()` is called without
# arguments (no HTTP server, no port binding).
mcp = FastMCP("apple-ecosystem")


@mcp.tool(
    description="Return macOS version — smoke test",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
)
def hello_apple() -> str:
    """Return macOS system version string."""
    return run_applescript("return system version of (system info)")


# Import tools module so all decorators execute at import time and register
# tools on `mcp`.
from . import tools as _tools  # noqa: E402,F401


def run() -> None:
    # FastMCP defaults to STDIO transport when transport is omitted.
    mcp.run()
