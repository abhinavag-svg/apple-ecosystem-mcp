#!/bin/bash
# PyPI Publishing Script for apple-ecosystem-mcp v0.3.0
#
# Usage:
#   1. Set your PyPI token:
#      export PYPI_TOKEN="pypi-YOUR_TOKEN_HERE"
#   2. Run this script:
#      bash PUBLISH_PYPI.sh

set -e

echo "🚀 Publishing apple-ecosystem-mcp v0.3.0 to PyPI..."
echo ""

# Check for token
if [ -z "$PYPI_TOKEN" ]; then
    echo "❌ Error: PYPI_TOKEN not set"
    echo ""
    echo "To publish, you need to:"
    echo "1. Get your PyPI API token from https://pypi.org/manage/account/token/"
    echo "2. Set it as an environment variable:"
    echo "   export PYPI_TOKEN=\"pypi-YOUR_TOKEN_HERE\""
    echo "3. Run this script again"
    echo ""
    exit 1
fi

# Verify build artifacts exist
if [ ! -f "dist/apple_ecosystem_mcp-0.3.0.tar.gz" ] || [ ! -f "dist/apple_ecosystem_mcp-0.3.0-py3-none-any.whl" ]; then
    echo "⚠️  Build artifacts not found. Building..."
    uv build
fi

echo "✅ Build artifacts ready:"
ls -lh dist/apple_ecosystem_mcp-0.3.0*
echo ""

# Publish
echo "📤 Publishing to PyPI..."
python -m twine upload dist/apple_ecosystem_mcp-0.3.0* \
    --username __token__ \
    --password "$PYPI_TOKEN" \
    --non-interactive

echo ""
echo "✅ Published successfully!"
echo ""
echo "📦 Package details:"
echo "   - Name: apple-ecosystem-mcp"
echo "   - Version: 0.3.0"
echo "   - PyPI: https://pypi.org/project/apple-ecosystem-mcp/"
echo ""
echo "🎉 Release complete!"
