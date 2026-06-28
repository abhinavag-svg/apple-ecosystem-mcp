from __future__ import annotations

import sys
import importlib.metadata

from .permissions import check_permissions
from . import mail_cli
from . import scheduler_cli
from .server import run
from . import __version__


def main() -> None:
    """Entry point: handle --version flag and start MCP server."""
    if "--version" in sys.argv:
        try:
            print(importlib.metadata.version("apple-ecosystem-mcp"))
        except importlib.metadata.PackageNotFoundError:
            print(__version__)
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "schedule":
        scheduler_cli.main(sys.argv[2:])
        return

    if len(sys.argv) > 1 and sys.argv[1] == "mail":
        mail_cli.main(sys.argv[2:])
        return

    check_permissions()
    run()
