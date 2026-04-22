.PHONY: build test lint format typecheck check install clean help

help:
	@echo "Apple Ecosystem MCP — Common Commands"
	@echo ""
	@echo "  make build       Compile TypeScript to dist/"
	@echo "  make test        Run full test suite"
	@echo "  make test-watch  Run tests in watch mode"
	@echo "  make lint        Check code style (ESLint)"
	@echo "  make format      Auto-format code (Prettier)"
	@echo "  make typecheck   Verify types without build"
	@echo "  make check       Run lint + test + typecheck (full validation)"
	@echo "  make clean       Remove dist/ and node_modules/"
	@echo "  make install     Install dependencies"
	@echo ""

install:
	npm install

build:
	npm run build

test:
	npm run test

test-watch:
	npm run test -- --watch

lint:
	npm run lint

format:
	npm run format

typecheck:
	npm run typecheck

check: lint typecheck test
	@echo "✓ All checks passed (lint, typecheck, test)"

clean:
	rm -rf dist/ node_modules/ coverage/
	@echo "✓ Cleaned dist/, node_modules/, coverage/"

dev:
	npm run dev

dev-test:
	npm run test -- --watch
