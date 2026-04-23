#!/usr/bin/env python3
"""Bootstrap entrypoint that delegates to uvx-installed apple-ecosystem-mcp."""

import subprocess
import sys

# Delegate to uvx-installed package
result = subprocess.run(
    ["uvx", "apple-ecosystem-mcp"],
    cwd=None,
)
sys.exit(result.returncode)
