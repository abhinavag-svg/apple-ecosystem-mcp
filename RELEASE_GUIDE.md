# Release Guide

This project ships through GitHub Releases as a Claude Desktop `.mcpb` bundle.

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
server/
src/
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

If you need to build the bundle without creating a release:

```bash
rm -rf mcpb
mkdir -p native/build
swiftc native/apple-ecosystem-helper.swift -o native/build/apple-ecosystem-helper
mkdir -p mcpb/contents
mkdir -p mcpb/contents/bin
cp manifest.json logo.svg README.md PRIVACY.md LICENSE pyproject.toml uv.lock mcpb/contents/
cp -r server src mcpb/contents/
cp native/build/apple-ecosystem-helper mcpb/contents/bin/
find mcpb/contents -type d -name __pycache__ -prune -exec rm -rf {} +
cd mcpb/contents && zip -q -r ../apple-ecosystem-mcp.mcpb .
```

The archive root should contain the manifest, bundled docs, runner, source tree, and native helper.
