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
echo "✅ Version bumped to $VERSION"
echo ""

# Commit version bump
echo "💾 Committing version bump..."
git add pyproject.toml manifest.json
git commit -m "chore: release v$VERSION"
echo "✅ Version bump committed"
echo ""

# Build MCPB
echo "📦 Building MCPB bundle..."
rm -rf mcpb
mkdir -p mcpb/contents
cp manifest.json logo.svg README.md LICENSE pyproject.toml uv.lock mcpb/contents/
cp -r server src mcpb/contents/
find mcpb/contents -type d -name __pycache__ -prune -exec rm -rf {} +
cd mcpb/contents
zip -q -r "../apple-ecosystem-mcp.mcpb" .
cd ../..
ls -lh "mcpb/apple-ecosystem-mcp.mcpb"
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
    --title "v$VERSION — Apple Ecosystem MCP Release" \
    --notes "Install the attached apple-ecosystem-mcp.mcpb in Claude Desktop. See README.md for setup and permissions."
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
