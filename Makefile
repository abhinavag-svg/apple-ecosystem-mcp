.PHONY: help install test build release clean

BUNDLE_ROOT_FILES = manifest.json logo.svg README.md PRIVACY.md LICENSE pyproject.toml uv.lock

help:
	@echo "Apple Ecosystem MCP"
	@echo ""
	@echo "  make install          Install Python dependencies"
	@echo "  make test             Run non-live tests"
	@echo "  make build            Build local DXT and MCPB bundles"
	@echo "  make release VERSION=X.Y.Z"
	@echo "  make clean            Remove generated artifacts"
	@echo ""

install:
	UV_CACHE_DIR=.uv-cache uv sync --dev

test:
	UV_CACHE_DIR=.uv-cache uv run pytest tests/ -k "not live" -v

build:
	rm -rf mcpb
	mkdir -p native/build
	swiftc native/apple-ecosystem-helper.swift -o native/build/apple-ecosystem-helper
	mkdir -p mcpb/contents
	mkdir -p mcpb/contents/bin
	cp $(BUNDLE_ROOT_FILES) mcpb/contents/
	cp -r server src mcpb/contents/
	cp native/build/apple-ecosystem-helper mcpb/contents/bin/
	find mcpb/contents -name .DS_Store -delete
	find mcpb/contents -type d -name __pycache__ -prune -exec rm -rf {} +
	cd mcpb/contents && zip -X -q -r ../apple-ecosystem-mcp.mcpb .
	cd mcpb/contents && zip -X -q -r ../apple-ecosystem-mcp.dxt .
	@unzip -Z1 mcpb/apple-ecosystem-mcp.mcpb | grep -qx manifest.json
	@unzip -Z1 mcpb/apple-ecosystem-mcp.mcpb | grep -qx README.md
	@unzip -Z1 mcpb/apple-ecosystem-mcp.mcpb | grep -qx PRIVACY.md
	@unzip -Z1 mcpb/apple-ecosystem-mcp.mcpb | grep -qx LICENSE
	@unzip -Z1 mcpb/apple-ecosystem-mcp.mcpb | grep -qx server/runner.py
	@unzip -Z1 mcpb/apple-ecosystem-mcp.mcpb | grep -qx bin/apple-ecosystem-helper
	@! unzip -Z1 mcpb/apple-ecosystem-mcp.mcpb | grep -E '(^|/)\.DS_Store$$|(^|/)docs/|(^|/)tests/|(^|/)\.claude/|(^|/)\.git/|(^|/)mcpb/|(^|/)dist/'
	@ls -lh mcpb/apple-ecosystem-mcp.mcpb
	@ls -lh mcpb/apple-ecosystem-mcp.dxt

release:
	@test -n "$(VERSION)" || (echo "Usage: make release VERSION=X.Y.Z" && exit 1)
	bash RELEASE.sh "$(VERSION)"

clean:
	rm -rf mcpb dist build coverage .pytest_cache .uv-cache native/build
	@echo "Cleaned generated artifacts"
