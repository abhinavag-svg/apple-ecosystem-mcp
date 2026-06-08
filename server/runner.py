#!/usr/bin/env python3
"""Bootstrap entrypoint for the bundled MCPB release."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

result = subprocess.run(
    ["uv", "run", "--project", str(ROOT), "python", "-m", "apple_ecosystem_mcp"],
    cwd=str(ROOT),
)
sys.exit(result.returncode)
