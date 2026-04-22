from __future__ import annotations

import sys
from importlib.metadata import version

from .permissions import check_permissions
from .server import run


def main() -> None:
    """Entry point: handle --version flag and start MCP server."""
    if "--version" in sys.argv:
        print(version("apple-ecosystem-mcp"))
        sys.exit(0)

    check_permissions()
    run()
