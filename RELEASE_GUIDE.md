# Release Guide

This project ships through GitHub Releases as a Claude Desktop MCPB bundle.

## Release Checklist

1. Run tests:
   ```bash
   make test
   ```
2. Release:
   ```bash
   bash RELEASE.sh X.Y.Z
   ```
3. Verify the GitHub release contains:
   ```text
   apple-ecosystem-mcp.mcpb
   ```
4. Download the MCPB from GitHub Releases, install it in Claude Desktop, and run `hello_apple`.
5. Update `docs/session-state.md` with any post-release notes.

## Manual Bundle Build

If you need to build the bundle without creating a release:

```bash
rm -rf mcpb
mkdir -p mcpb/contents
cp manifest.json logo.svg README.md LICENSE pyproject.toml uv.lock mcpb/contents/
cp -r server src mcpb/contents/
find mcpb/contents -type d -name __pycache__ -prune -exec rm -rf {} +
cd mcpb/contents
zip -q -r ../apple-ecosystem-mcp.mcpb .
cd ../..
```

The archive root must contain `manifest.json`, `server/`, `src/`, `pyproject.toml`, and `uv.lock`.
