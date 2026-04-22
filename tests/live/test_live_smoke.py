import os

import pytest


pytestmark = pytest.mark.skipif(
    not os.getenv("APPLE_MCP_LIVE_TESTS"),
    reason="Set APPLE_MCP_LIVE_TESTS=1 to run optional live macOS tests",
)

# Implementations will be added in Phase 5 (one smoke test per subsystem).
