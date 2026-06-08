.PHONY: help install test build release clean

help:
	@echo "Apple Ecosystem MCP"
	@echo ""
	@echo "  make install          Install Python dependencies"
	@echo "  make test             Run non-live tests"
	@echo "  make build            Build local MCPB bundle"
	@echo "  make release VERSION=X.Y.Z"
	@echo "  make clean            Remove generated artifacts"
	@echo ""

install:
	UV_CACHE_DIR=.uv-cache uv sync --dev

test:
	UV_CACHE_DIR=.uv-cache uv run pytest tests/ -k "not live" -v

build:
	rm -rf mcpb
	mkdir -p mcpb/contents
	cp manifest.json logo.svg README.md LICENSE pyproject.toml uv.lock mcpb/contents/
	cp -r server src mcpb/contents/
	find mcpb/contents -type d -name __pycache__ -prune -exec rm -rf {} +
	cd mcpb/contents && zip -q -r ../apple-ecosystem-mcp.mcpb .
	@ls -lh mcpb/apple-ecosystem-mcp.mcpb

release:
	@test -n "$(VERSION)" || (echo "Usage: make release VERSION=X.Y.Z" && exit 1)
	bash RELEASE.sh "$(VERSION)"

clean:
	rm -rf mcpb dist build coverage .pytest_cache .uv-cache
	@echo "Cleaned generated artifacts"
