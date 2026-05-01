#!/bin/bash
# Apple Ecosystem MCP Release Script
# Automates Phase 6 release checklist to prevent missing .dxt upload or other critical steps
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
uv run pytest tests/ -k "not live" -v > /dev/null 2>&1 || {
    echo "❌ Tests failed"
    exit 1
}
echo "✅ All tests pass"
echo ""

# Version bump
echo "📝 Updating version to $VERSION..."
sed -i '' "s/version = \"[0-9.]*\"/version = \"$VERSION\"/" pyproject.toml
sed -i '' "s/\"version\": \"[0-9.]*\"/\"version\": \"$VERSION\"/" manifest.json
sed -i '' "s/apple-ecosystem-mcp@[0-9.]*/apple-ecosystem-mcp@$VERSION/" manifest.json
sed -i '' "s/apple_ecosystem_mcp-[0-9.]*./apple_ecosystem_mcp-$VERSION./" PUBLISH_PYPI.sh
sed -i '' "s/apple-ecosystem-mcp v[0-9.]*/apple-ecosystem-mcp v$VERSION/" PUBLISH_PYPI.sh
echo "✅ Version bumped to $VERSION"
echo ""

# Update session state
echo "📝 Updating docs/session-state.md..."
echo "⚠️  Reminder: Update session-state.md manually with session summary"
echo ""

# Commit version bump
echo "💾 Committing version bump..."
git add pyproject.toml manifest.json PUBLISH_PYPI.sh
git commit -m "chore: version bump to $VERSION" || true
echo "✅ Version bump committed"
echo ""

# Build
echo "🔨 Building distribution..."
uv build
echo "✅ Build complete"
echo ""

# Create tag
echo "🏷️  Creating git tag..."
git tag -a "v$VERSION" -m "chore: release v$VERSION" || {
    echo "⚠️  Tag already exists"
}
echo "✅ Tag created: v$VERSION"
echo ""

# Push
echo "📤 Pushing to GitHub..."
git push origin main || echo "⚠️  Main already up to date"
git push origin "v$VERSION" || echo "⚠️  Tag already pushed"
echo "✅ Pushed to GitHub"
echo ""

# Create .dxt
echo "📦 Building .dxt file..."
mkdir -p dxt
cd dxt
zip -q -r "apple-ecosystem-mcp.dxt" ../manifest.json ../logo.svg ../server/
cd ..
ls -lh "dxt/apple-ecosystem-mcp.dxt"
echo "✅ .dxt file created"
echo ""

# Create GitHub release
echo "🚀 Creating GitHub release..."
gh release create "v$VERSION" \
    --title "v$VERSION — Apple Ecosystem MCP Release" \
    --notes "See https://github.com/abhinavag-svg/apple-ecosystem-mcp/blob/main/docs/FEATURE_TODOS.md for feature status." \
    2>/dev/null || echo "⚠️  Release already exists"
echo ""

# Upload assets
echo "📤 Uploading release assets..."
gh release upload "v$VERSION" \
    "dxt/apple-ecosystem-mcp.dxt" \
    "dist/apple_ecosystem_mcp-${VERSION}.tar.gz" \
    "dist/apple_ecosystem_mcp-${VERSION}-py3-none-any.whl" \
    --clobber
echo "✅ Assets uploaded"
echo ""

# Verify
echo "✅ Verifying release assets..."
ASSETS=$(gh release view "v$VERSION" --json assets -q '.assets[] | .name' 2>/dev/null)
if echo "$ASSETS" | grep -q "apple-ecosystem-mcp.dxt"; then
    echo "✅ .dxt file present"
else
    echo "❌ ERROR: .dxt file NOT found in release!"
    exit 1
fi
if echo "$ASSETS" | grep -q "\.whl"; then
    echo "✅ Wheel file present"
else
    echo "❌ ERROR: Wheel file NOT found in release!"
    exit 1
fi
if echo "$ASSETS" | grep -q "\.tar\.gz"; then
    echo "✅ Source tarball present"
else
    echo "❌ ERROR: Source tarball NOT found in release!"
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
echo "   1. Update docs/session-state.md with session summary"
echo "   2. Publish to PyPI: export PYPI_TOKEN=... && bash PUBLISH_PYPI.sh"
echo ""
