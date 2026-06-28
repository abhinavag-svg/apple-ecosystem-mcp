.PHONY: help install test build build-node-mcpb build-uv-mcpb build-companion-app release clean

BUNDLE_ROOT_FILES = manifest.json logo.svg README.md PRIVACY.md LICENSE pyproject.toml uv.lock package.json package-lock.json
NODE_BUNDLE_ROOT_FILES = manifest.node.json logo.svg README.md PRIVACY.md LICENSE pyproject.toml uv.lock package.json package-lock.json
HELPER_SWIFTC = CLANG_MODULE_CACHE_PATH=/private/tmp/apple-ecosystem-clang-cache swiftc native/apple-ecosystem-helper.swift \
	-Xlinker -sectcreate \
	-Xlinker __TEXT \
	-Xlinker __info_plist \
	-Xlinker native/apple-ecosystem-helper.Info.plist \
	-o native/build/apple-ecosystem-helper

help:
	@echo "Apple Ecosystem MCP"
	@echo ""
	@echo "  make install          Install Python dependencies"
	@echo "  make test             Run non-live tests"
	@echo "  make build            Build local Node-runtime MCPB bundle"
	@echo "  make build-node-mcpb  Build local Node-wrapper MCPB bundle"
	@echo "  make build-uv-mcpb    Build future UV-runtime MCPB bundle"
	@echo "  make build-companion-app  Build local macOS companion app"
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
	$(HELPER_SWIFTC)
	mkdir -p mcpb/contents
	mkdir -p mcpb/contents/bin
	mkdir -p mcpb/contents/server
	mkdir -p mcpb/contents/node_modules
	cp $(BUNDLE_ROOT_FILES) mcpb/contents/
	cp -r src mcpb/contents/
	cp server/runner.py mcpb/contents/server/
	cp node/server/node-launcher.mjs mcpb/contents/server/
	env UV_CACHE_DIR=/private/tmp/uv-cache uv run python scripts/vendor_python_deps.py mcpb/contents/server/lib
	cp native/build/apple-ecosystem-helper mcpb/contents/bin/
	rm -rf mcpb/contents/.venv
	find mcpb/contents -name .DS_Store -delete
	find mcpb/contents -type d -name __pycache__ -prune -exec rm -rf {} +
	cd mcpb/contents && zip -X -q -r ../apple-ecosystem-mcp.mcpb .
	python3 scripts/validate_mcpb.py --mode node mcpb/apple-ecosystem-mcp.mcpb
	@ls -lh mcpb/apple-ecosystem-mcp.mcpb

build-uv-mcpb:
	rm -rf mcpb-uv
	mkdir -p native/build
	$(HELPER_SWIFTC)
	mkdir -p mcpb-uv/contents
	mkdir -p mcpb-uv/contents/bin
	cp manifest.uv.json mcpb-uv/contents/manifest.json
	cp logo.svg README.md PRIVACY.md LICENSE pyproject.toml uv.lock mcpb-uv/contents/
	cp -r src mcpb-uv/contents/
	cp native/build/apple-ecosystem-helper mcpb-uv/contents/bin/
	find mcpb-uv/contents -name .DS_Store -delete
	find mcpb-uv/contents -type d -name __pycache__ -prune -exec rm -rf {} +
	cd mcpb-uv/contents && zip -X -q -r ../apple-ecosystem-mcp-uv.mcpb .
	python3 scripts/validate_mcpb.py --mode uv mcpb-uv/apple-ecosystem-mcp-uv.mcpb
	@ls -lh mcpb-uv/apple-ecosystem-mcp-uv.mcpb

build-node-mcpb:
	rm -rf mcpb-node
	mkdir -p native/build
	$(HELPER_SWIFTC)
	mkdir -p mcpb-node/contents
	mkdir -p mcpb-node/contents/bin
	mkdir -p mcpb-node/contents/server
	mkdir -p mcpb-node/contents/node_modules
	cp manifest.node.json mcpb-node/contents/manifest.json
	cp logo.svg README.md PRIVACY.md LICENSE pyproject.toml uv.lock package.json package-lock.json mcpb-node/contents/
	cp -r src mcpb-node/contents/
	cp server/runner.py mcpb-node/contents/server/
	cp node/server/node-launcher.mjs mcpb-node/contents/server/
	env UV_CACHE_DIR=/private/tmp/uv-cache uv run python scripts/vendor_python_deps.py mcpb-node/contents/server/lib
	cp native/build/apple-ecosystem-helper mcpb-node/contents/bin/
	rm -rf mcpb-node/contents/.venv
	find mcpb-node/contents -name .DS_Store -delete
	find mcpb-node/contents -type d -name __pycache__ -prune -exec rm -rf {} +
	cd mcpb-node/contents && zip -X -q -r ../apple-ecosystem-mcp-node.mcpb .
	python3 scripts/validate_mcpb.py --mode node mcpb-node/apple-ecosystem-mcp-node.mcpb
	@ls -lh mcpb-node/apple-ecosystem-mcp-node.mcpb

build-companion-app:
	rm -rf "native/build/Apple Ecosystem.app"
	mkdir -p "native/build/Apple Ecosystem.app/Contents/MacOS"
	cp native/companion/Info.plist "native/build/Apple Ecosystem.app/Contents/Info.plist"
	CLANG_MODULE_CACHE_PATH=/private/tmp/apple-ecosystem-clang-cache swiftc native/companion/AppleEcosystemControl.swift \
		-parse-as-library \
		-framework AppKit \
		-framework EventKit \
		-framework Contacts \
		-o "native/build/Apple Ecosystem.app/Contents/MacOS/AppleEcosystemControl"
	@echo "Built native/build/Apple Ecosystem.app"

release:
	@test -n "$(VERSION)" || (echo "Usage: make release VERSION=X.Y.Z" && exit 1)
	bash RELEASE.sh "$(VERSION)"

clean:
	rm -rf mcpb dist build coverage .pytest_cache .uv-cache native/build
	@echo "Cleaned generated artifacts"
