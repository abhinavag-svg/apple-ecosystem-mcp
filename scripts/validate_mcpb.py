#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import posixpath
import sys
import zipfile
from pathlib import Path
from typing import Any


FORBIDDEN_PATH_PARTS = {
    ".DS_Store",
    ".claude",
    ".git",
    "dist",
    "docs",
    "mcpb",
    "mcpb-node",
    "tests",
}

AUTHOR_GITHUB_URL = "https://github.com/abhinavag-svg"


def _read_manifest(bundle: zipfile.ZipFile) -> dict[str, Any]:
    try:
        raw = bundle.read("manifest.json")
    except KeyError as exc:
        raise ValueError("manifest.json is missing") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest.json is invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("manifest.json must be a JSON object")
    return data


def _assert_present(names: set[str], required: list[str]) -> None:
    missing = [name for name in required if name not in names]
    if missing:
        raise ValueError(f"bundle is missing required files: {', '.join(missing)}")


def _assert_forbidden_paths(names: set[str]) -> None:
    bad: list[str] = []
    for name in names:
        parts = [part for part in posixpath.normpath(name).split("/") if part]
        if ".DS_Store" in parts:
            bad.append(name)
            continue
        if parts and parts[0] in FORBIDDEN_PATH_PARTS:
            bad.append(name)
    if bad:
        raise ValueError(f"bundle contains forbidden local artifacts: {', '.join(sorted(bad)[:10])}")


def _assert_no_host_commands(manifest: dict[str, Any]) -> None:
    server = manifest.get("server")
    if not isinstance(server, dict):
        raise ValueError("manifest server must be an object")
    mcp_config = server.get("mcp_config")
    if mcp_config is None:
        return
    if not isinstance(mcp_config, dict):
        raise ValueError("server.mcp_config must be an object when present")
    command = str(mcp_config.get("command", ""))
    args = [str(arg) for arg in mcp_config.get("args", []) if arg is not None]
    values = [command, *args]
    if any(value in {"python", "python3", "uv"} for value in values):
        raise ValueError("uv MCPB must not invoke user-installed python, python3, or uv")
    if any(value.startswith("/") for value in values):
        raise ValueError("uv MCPB must not invoke absolute local paths")


def _assert_no_host_runtime_commands(manifest: dict[str, Any]) -> None:
    server = manifest.get("server")
    if not isinstance(server, dict):
        raise ValueError("manifest server must be an object")
    mcp_config = server.get("mcp_config")
    if not isinstance(mcp_config, dict):
        raise ValueError("binary MCPB must define server.mcp_config")
    values = [str(server.get("entry_point", "")), str(mcp_config.get("command", ""))]
    values.extend(str(arg) for arg in mcp_config.get("args", []) if arg is not None)
    forbidden = {"node", "python", "python3", "uv"}
    if any(value in forbidden for value in values):
        raise ValueError("binary MCPB must not invoke host node, python, python3, or uv")


def _assert_author_points_to_github(manifest: dict[str, Any]) -> None:
    author = manifest.get("author")
    if not isinstance(author, dict):
        raise ValueError("manifest author must be an object")
    if author.get("url") != AUTHOR_GITHUB_URL:
        raise ValueError(f"manifest author.url must be {AUTHOR_GITHUB_URL}")


def validate_binary_bundle(bundle: zipfile.ZipFile) -> None:
    names = set(bundle.namelist())
    manifest = _read_manifest(bundle)
    server = manifest.get("server")
    compatibility = manifest.get("compatibility")
    if not isinstance(server, dict):
        raise ValueError("manifest server must be an object")
    if not isinstance(compatibility, dict):
        raise ValueError("manifest compatibility must be an object")
    if manifest.get("manifest_version") != "0.4":
        raise ValueError("manifest_version must be 0.4")
    _assert_author_points_to_github(manifest)
    if server.get("type") != "binary":
        raise ValueError("server.type must be binary")
    if server.get("entry_point") != "bin/apple-ecosystem-mcp":
        raise ValueError("server.entry_point must point at bin/apple-ecosystem-mcp")
    mcp_config = server.get("mcp_config")
    if not isinstance(mcp_config, dict):
        raise ValueError("binary MCPB must define server.mcp_config")
    if mcp_config.get("command") != "${__dirname}/bin/apple-ecosystem-mcp":
        raise ValueError(
            "binary MCPB server.mcp_config.command must point at ${__dirname}/bin/apple-ecosystem-mcp"
        )
    runtimes = compatibility.get("runtimes")
    if runtimes:
        raise ValueError("binary MCPB must not declare host runtimes")
    _assert_no_host_runtime_commands(manifest)
    _assert_present(
        names,
        [
            "manifest.json",
            "README.md",
            "PRIVACY.md",
            "LICENSE",
            "logo.svg",
            "bin/apple-ecosystem-mcp",
            "bin/_internal/",
            "bin/apple-ecosystem-helper",
        ],
    )
    _assert_forbidden_paths(names)


def validate_uv_bundle(bundle: zipfile.ZipFile) -> None:
    names = set(bundle.namelist())
    manifest = _read_manifest(bundle)
    server = manifest.get("server")
    if not isinstance(server, dict):
        raise ValueError("manifest server must be an object")
    if manifest.get("manifest_version") != "0.4":
        raise ValueError("manifest_version must be 0.4")
    _assert_author_points_to_github(manifest)
    if server.get("type") != "uv":
        raise ValueError("server.type must be uv")
    if server.get("entry_point") != "src/apple_ecosystem_mcp/__main__.py":
        raise ValueError("server.entry_point must point at src/apple_ecosystem_mcp/__main__.py")
    _assert_no_host_commands(manifest)
    _assert_present(
        names,
        [
            "manifest.json",
            "README.md",
            "PRIVACY.md",
            "LICENSE",
            "logo.svg",
            "pyproject.toml",
            "uv.lock",
            "bin/apple-ecosystem-helper",
            "src/apple_ecosystem_mcp/__main__.py",
        ],
    )
    _assert_forbidden_paths(names)


def validate_node_bundle(bundle: zipfile.ZipFile) -> None:
    names = set(bundle.namelist())
    manifest = _read_manifest(bundle)
    server = manifest.get("server")
    compatibility = manifest.get("compatibility")
    if not isinstance(server, dict):
        raise ValueError("manifest server must be an object")
    if not isinstance(compatibility, dict):
        raise ValueError("manifest compatibility must be an object")
    if manifest.get("manifest_version") != "0.4":
        raise ValueError("manifest_version must be 0.4")
    _assert_author_points_to_github(manifest)
    if server.get("type") != "node":
        raise ValueError("server.type must be node")
    if server.get("entry_point") != "server/node-launcher.mjs":
        raise ValueError("server.entry_point must point at server/node-launcher.mjs")
    runtimes = compatibility.get("runtimes")
    if not isinstance(runtimes, dict) or "node" not in runtimes:
        raise ValueError("node MCPB must declare compatibility.runtimes.node")
    _assert_present(
        names,
        [
            "manifest.json",
            "README.md",
            "PRIVACY.md",
            "LICENSE",
            "logo.svg",
            "package.json",
            "package-lock.json",
            "node_modules/",
            "server/lib/fastmcp/",
            "server/lib/mcp/",
            "server/lib/pydantic_core/",
            "server/node-launcher.mjs",
            "server/runner.py",
            "src/apple_ecosystem_mcp/__main__.py",
            "bin/apple-ecosystem-helper",
        ],
    )
    _assert_forbidden_paths(names)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Apple Ecosystem MCPB bundles")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--mode", choices=["binary", "uv", "node"], required=True)
    args = parser.parse_args(argv)

    try:
        with zipfile.ZipFile(args.bundle) as bundle:
            if args.mode == "binary":
                validate_binary_bundle(bundle)
            elif args.mode == "uv":
                validate_uv_bundle(bundle)
            else:
                validate_node_bundle(bundle)
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
