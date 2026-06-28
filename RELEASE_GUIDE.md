# Release Guide

This project ships through GitHub Releases as a Claude Desktop `.mcpb` bundle.
For local builds, the primary bundle uses a Node.js launcher because current
Claude Desktop builds validate local bundles as Node/Python/Binary extensions.
The future MCPB `uv` runtime bundle is available as a separate local target.

## Release Checklist

1. Run non-live tests:

```bash
make test
```

2. Build the bundle:

```bash
make build
```

3. Verify the bundle contents include:

```text
manifest.json
README.md
PRIVACY.md
LICENSE
pyproject.toml
uv.lock
src/
src/apple_ecosystem_mcp/__main__.py
server/node-launcher.mjs
bin/apple-ecosystem-helper
```

4. Push the release commit and create a GitHub release with:

```bash
bash RELEASE.sh X.Y.Z
```

5. Confirm the GitHub release contains:

```text
apple-ecosystem-mcp.mcpb
```

6. Install the MCPB in Claude Desktop and smoke-test a few read-only tools such as:

```text
apple_inventory
notes_list
scheduled_tasks_list
```

## Manual Bundle Build

If you need to build the primary bundle without creating a release:

```bash
rm -rf mcpb
mkdir -p native/build
swiftc native/apple-ecosystem-helper.swift -o native/build/apple-ecosystem-helper
mkdir -p mcpb/contents
mkdir -p mcpb/contents/bin
mkdir -p mcpb/contents/server
mkdir -p mcpb/contents/node_modules
cp manifest.json logo.svg README.md PRIVACY.md LICENSE pyproject.toml uv.lock package.json package-lock.json mcpb/contents/
cp -r src mcpb/contents/
cp server/runner.py node/server/node-launcher.mjs mcpb/contents/server/
cp native/build/apple-ecosystem-helper mcpb/contents/bin/
find mcpb/contents -type d -name __pycache__ -prune -exec rm -rf {} +
cd mcpb/contents && zip -q -r ../apple-ecosystem-mcp.mcpb .
```

The archive root should contain the manifest, bundled docs, Node launcher, source tree, lockfile, and native helper.

For Anthropic Node.js compatibility testing, use the separate local target:

```bash
make build-node-mcpb
```

That bundle is intentionally separate from the primary `uv` bundle.

For future MCPB `uv` runtime testing, use:

```bash
make build-uv-mcpb
```
