# Release Guide — Apple Ecosystem MCP v0.1.0

This document provides step-by-step instructions for publishing version 0.1.0 to PyPI and GitHub.

## Pre-Release Checklist

- ✅ All 151 tests pass: `uv run pytest tests/ -v`
- ✅ Version flag works: `uv run python -m apple_ecosystem_mcp --version` → `0.1.0`
- ✅ Package builds cleanly: `uv build` → dist/apple_ecosystem_mcp-0.1.0.tar.gz and .whl
- ✅ manifest.json created for Desktop Extension
- ✅ apple-ecosystem-mcp.dxt built and ready
- ✅ README updated with complete tool catalog and permissions guide
- ✅ All changes committed to git

## Step 1: Push to GitHub

First, add your GitHub remote (if not already configured):

```bash
git remote add origin https://github.com/abhinavagrawal/apple-ecosystem-mcp.git
```

Push the main branch and the release tag:

```bash
git push origin main
git push origin v0.1.0
```

## Step 2: Create GitHub Release

Using the GitHub CLI:

```bash
gh release create v0.1.0 apple-ecosystem-mcp.dxt \
  --title "Apple Ecosystem MCP v0.1.0" \
  --notes "First release: complete MCP server for Apple Mail, Calendar, Contacts, Reminders, and iCloud Drive.

## Installation

**Claude Desktop users:** Download the \`apple-ecosystem-mcp.dxt\` file and double-click to install.

**Claude Code users:** Use \`uvx apple-ecosystem-mcp\` after publishing to PyPI.

## What's Included

- **34 tools** across 5 Apple apps
- **Mail**: search, read, send, move, flag, delete (8 tools)
- **Calendar**: list, create, update, delete, find free time (7 tools)
- **Contacts**: search, read, create, update, groups (5 tools)
- **Reminders**: list, create, complete, delete (5 tools)
- **iCloud Drive**: read, write, move, delete, search (5 tools)

## Requirements

- macOS 13+
- Claude Desktop (recommended) or Claude Code
- macOS permissions for Automation and Full Disk Access

See [README](https://github.com/abhinavagrawal/apple-ecosystem-mcp#readme) for setup instructions.
"
```

Or create it manually on GitHub at:
```
https://github.com/abhinavagrawal/apple-ecosystem-mcp/releases/new
```

Upload `apple-ecosystem-mcp.dxt` as an asset.

## Step 3: Publish to PyPI

### Option A: Using uv (Recommended)

1. Create a PyPI API token at https://pypi.org/account/ (account settings → API tokens)
2. Set the token as an environment variable:
   ```bash
   export UV_PUBLISH_TOKEN="pypi-AgEIcHlwaS5vcmc..."
   ```
3. Publish:
   ```bash
   uv publish
   ```

### Option B: Using twine (Alternative)

1. Create a PyPI API token at https://pypi.org/account/ (account settings → API tokens)
2. Create `~/.pypirc`:
   ```ini
   [distutils]
   index-servers = pypi

   [pypi]
   repository: https://upload.pypi.org/legacy/
   username: __token__
   password: pypi-AgEIcHlwaS5vcmc...
   ```
3. Publish:
   ```bash
   twine upload dist/*
   ```

## Step 4: Verify PyPI Installation

Once published (may take a few minutes), verify installation works:

```bash
# In a new shell (no venv active)
uvx apple-ecosystem-mcp --version
# Expected: 0.1.0

# Try in Claude Desktop config (macOS only)
# Update ~/Library/Application Support/Claude/claude_desktop_config.json:
{
  "mcpServers": {
    "apple-ecosystem": {
      "command": "uvx",
      "args": ["apple-ecosystem-mcp"]
    }
  }
}
```

Restart Claude Desktop and call `hello_apple` to verify.

## Post-Release

1. ✅ GitHub release created with .dxt attached
2. ✅ PyPI package published
3. ✅ uvx installation verified
4. ✅ Claude Desktop integration tested

## Rollback (if needed)

If you need to remove a version from PyPI:

```bash
# Yanking is performed on PyPI.org directly
# Visit https://pypi.org/project/apple-ecosystem-mcp/
# Click the version and select "Yank"
```

## Future Releases

For version 0.2.0 and beyond:

1. Update `version = "0.X.Y"` in `pyproject.toml`
2. Update manifest.json version
3. Rebuild .dxt: `zip -j apple-ecosystem-mcp.dxt manifest.json`
4. Commit changes: `git commit -am "feat: phase X ..."`
5. Tag and push: `git tag v0.X.Y && git push origin main && git push origin v0.X.Y`
6. Follow steps 2–4 above for each release

---

**Notes:**
- The `.dxt` file is the primary distribution for Claude Desktop users — ensure it's updated and tested before release
- PyPI distribution via `uvx` is for Claude Code users and advanced developers
- Keep version numbers in sync: `pyproject.toml`, `manifest.json`, and git tags must all match
