#!/bin/bash
# Apple Ecosystem MCP Release Script
# Builds and uploads the GitHub-only MCPB desktop bundle.
# Usage: bash RELEASE.sh 0.3.1

set -e

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
    echo "❌ Error: Version required"
    echo "Usage: bash RELEASE.sh 0.3.1"
    exit 1
fi

verify_bundle_contents() {
    local bundle="$1"
    local listing
    listing=$(unzip -Z1 "$bundle")

    for required in manifest.json README.md PRIVACY.md LICENSE pyproject.toml uv.lock package.json package-lock.json server/node-launcher.mjs src/apple_ecosystem_mcp/__main__.py bin/apple-ecosystem-helper; do
        if ! echo "$listing" | grep -qx "$required"; then
            echo "❌ ERROR: Required bundle file missing: $required"
            exit 1
        fi
    done

    if echo "$listing" | grep -E '(^|/)\.DS_Store$|(^|/)docs/|(^|/)tests/|(^|/)\.claude/|(^|/)\.git/|(^|/)mcpb/|(^|/)dist/' >/dev/null; then
        echo "❌ ERROR: Bundle contains forbidden local/docs/test artifacts"
        echo "$listing" | grep -E '(^|/)\.DS_Store$|(^|/)docs/|(^|/)tests/|(^|/)\.claude/|(^|/)\.git/|(^|/)mcpb/|(^|/)dist/'
        exit 1
    fi
}

echo "🚀 Starting release for v$VERSION..."
echo ""

# Pre-release checks
echo "📋 Pre-Release Checks..."
if git status --porcelain | grep -q .; then
    echo "❌ Error: Uncommitted changes exist"
    git status
    exit 1
fi
echo "✅ Working tree clean"

echo "✅ Running tests..."
UV_CACHE_DIR=.uv-cache uv run pytest tests/ -k "not live" -v > /dev/null 2>&1 || {
    echo "❌ Tests failed"
    exit 1
}
echo "✅ All tests pass"
echo ""

# Version bump
echo "📝 Updating version to $VERSION..."
sed -i '' "s/version = \"[0-9.]*\"/version = \"$VERSION\"/" pyproject.toml
sed -i '' "s/\"version\": \"[0-9.]*\"/\"version\": \"$VERSION\"/" manifest.json
sed -i '' "s/\"version\": \"[0-9.]*\"/\"version\": \"$VERSION\"/" manifest.uv.json
sed -i '' "s/\"version\": \"[0-9.]*\"/\"version\": \"$VERSION\"/" manifest.node.json
sed -i '' "s/\"version\": \"[0-9.]*\"/\"version\": \"$VERSION\"/" package.json
sed -i '' "s/\"version\": \"[0-9.]*\"/\"version\": \"$VERSION\"/" package-lock.json
UV_CACHE_DIR=.uv-cache uv lock
echo "✅ Version bumped to $VERSION"
echo ""

# Commit version bump
echo "💾 Committing version bump..."
git add pyproject.toml manifest.json manifest.uv.json manifest.node.json package.json package-lock.json uv.lock
git commit -m "chore: release v$VERSION"
echo "✅ Version bump committed"
echo ""

# Build MCPB
echo "📦 Building MCPB bundle..."
rm -rf mcpb
mkdir -p native/build
CLANG_MODULE_CACHE_PATH=/private/tmp/apple-ecosystem-clang-cache swiftc native/apple-ecosystem-helper.swift \
    -Xlinker -sectcreate \
    -Xlinker __TEXT \
    -Xlinker __info_plist \
    -Xlinker native/apple-ecosystem-helper.Info.plist \
    -o native/build/apple-ecosystem-helper
mkdir -p mcpb/contents
mkdir -p mcpb/contents/bin
mkdir -p mcpb/contents/server
mkdir -p mcpb/contents/node_modules
cp manifest.json logo.svg README.md PRIVACY.md LICENSE pyproject.toml uv.lock package.json package-lock.json mcpb/contents/
cp -r src mcpb/contents/
cp server/runner.py mcpb/contents/server/
cp node/server/node-launcher.mjs mcpb/contents/server/
env UV_CACHE_DIR=/private/tmp/uv-cache uv run python scripts/vendor_python_deps.py mcpb/contents/server/lib
cp native/build/apple-ecosystem-helper mcpb/contents/bin/
find mcpb/contents -name .DS_Store -delete
find mcpb/contents -type d -name __pycache__ -prune -exec rm -rf {} +
cd mcpb/contents
zip -q -r "../apple-ecosystem-mcp.mcpb" .
cd ../..
ls -lh "mcpb/apple-ecosystem-mcp.mcpb"
verify_bundle_contents "mcpb/apple-ecosystem-mcp.mcpb"
python3 scripts/validate_mcpb.py --mode node mcpb/apple-ecosystem-mcp.mcpb
echo "✅ MCPB bundle created"
echo ""

# Create tag
echo "🏷️  Creating git tag..."
git tag -a "v$VERSION" -m "chore: release v$VERSION"
echo "✅ Tag created: v$VERSION"
echo ""

# Push
echo "📤 Pushing to GitHub..."
git push origin main || echo "⚠️  Main already up to date"
git push origin "v$VERSION" || echo "⚠️  Tag already pushed"
echo "✅ Pushed to GitHub"
echo ""

# Create GitHub release
echo "🚀 Creating GitHub release..."
gh release create "v$VERSION" \
    --title "v$VERSION — Apple Ecosystem MCPB Installability And Permission UX" \
    --notes "Apple Ecosystem MCP v$VERSION focuses on making the Claude Desktop extension install cleanly as an MCPB while preserving the existing Apple tool behavior.

Highlights:
- Ships the primary MCPB as a Node-runtime bundle for current Claude Desktop compatibility.
- Adds a thin Node launcher that starts the existing Python tool engine with vendored dependencies.
- Keeps a separate future UV-runtime manifest/build target for Claude builds that support server.type = uv.
- Adds stricter MCPB validation for manifest version, author GitHub URL, required bundled files, forbidden local artifacts, and runtime commands.
- Embeds macOS privacy usage descriptions in the native helper for Calendar, Contacts, and Reminders permission prompts.
- Adds an original local companion app skeleton for permission/status workflows inspired by native macOS control-plane patterns.
- Improves Contacts and Reminders fallback behavior when native framework access is denied or unavailable.
- Fixes the Contacts AppleScript fallback compile error seen during live lookup after native permission denial.
- Updates README and release guidance for the install-first MCPB path, Node compatibility, and future UV bundle.
- Includes the latest README screenshot added directly on GitHub before this release.

Install the attached apple-ecosystem-mcp.mcpb in Claude Desktop. See README.md for setup, permissions, troubleshooting, and support."
echo ""

# Upload assets
echo "📤 Uploading release assets..."
gh release upload "v$VERSION" \
    "mcpb/apple-ecosystem-mcp.mcpb" \
    --clobber
echo "✅ Assets uploaded"
echo ""

# Verify
echo "✅ Verifying release assets..."
ASSETS=$(gh release view "v$VERSION" --json assets -q '.assets[] | .name' 2>/dev/null)
if echo "$ASSETS" | grep -q "apple-ecosystem-mcp.mcpb"; then
    echo "✅ MCPB file present"
else
    echo "❌ ERROR: MCPB file NOT found in release!"
    exit 1
fi
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Release v$VERSION Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📦 Release assets:"
gh release view "v$VERSION" --json assets -q '.assets[] | "  - \(.name) (\(.size | tonumber / 1024 | floor) KB)"'
echo ""
echo "🔗 GitHub Release:"
echo "   https://github.com/abhinavag-svg/apple-ecosystem-mcp/releases/tag/v$VERSION"
echo ""
echo "📚 Next steps:"
echo "   1. Download and install the MCPB from GitHub Releases to verify Claude Desktop"
echo "   2. Update docs/session-state.md with any post-release notes"
echo ""
