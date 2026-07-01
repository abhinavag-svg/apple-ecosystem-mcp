from __future__ import annotations

import json
import importlib.util
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHOR_GITHUB_URL = "https://github.com/abhinavag-svg"
VALIDATOR_PATH = ROOT / "scripts" / "validate_mcpb.py"
spec = importlib.util.spec_from_file_location("validate_mcpb", VALIDATOR_PATH)
assert spec is not None
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)
validate_node_bundle = validator.validate_node_bundle
validate_binary_bundle = validator.validate_binary_bundle
validate_uv_bundle = validator.validate_uv_bundle


def test_primary_manifest_uses_self_contained_binary_runtime():
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == "0.4"
    assert manifest["author"]["url"] == AUTHOR_GITHUB_URL
    assert manifest["version"] == "1.1.2"
    assert manifest["server"] == {
        "type": "binary",
        "entry_point": "bin/apple-ecosystem-mcp",
        "mcp_config": {
            "command": "${__dirname}/bin/apple-ecosystem-mcp",
            "args": [],
            "env": {},
        },
    }
    assert "runtimes" not in manifest["compatibility"]


def test_future_uv_manifest_uses_host_managed_uv_runtime_without_host_command():
    manifest = json.loads((ROOT / "manifest.uv.json").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == "0.4"
    assert manifest["author"]["url"] == AUTHOR_GITHUB_URL
    assert manifest["server"] == {
        "type": "uv",
        "entry_point": "src/apple_ecosystem_mcp/__main__.py",
    }


def test_node_manifest_is_separate_node_runtime():
    manifest = json.loads((ROOT / "manifest.node.json").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == "0.4"
    assert manifest["author"]["url"] == AUTHOR_GITHUB_URL
    assert manifest["server"]["type"] == "node"
    assert manifest["server"]["entry_point"] == "server/node-launcher.mjs"
    assert manifest["compatibility"]["runtimes"]["node"] == ">=18.0.0"


def test_makefile_signs_native_helper_with_stable_bundle_id():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "HELPER_BUNDLE_ID = com.abhinavagrawal.apple-ecosystem-mcp.helper" in makefile
    assert "codesign --force --sign - --identifier $(HELPER_BUNDLE_ID)" in makefile
    assert "SERVER_BUNDLE_ID = com.abhinavagrawal.apple-ecosystem-mcp.server" in makefile
    assert "codesign --force --sign - --identifier $(SERVER_BUNDLE_ID)" in makefile


def test_binary_bundle_validator_accepts_expected_archive(tmp_path):
    bundle_path = tmp_path / "apple-ecosystem-mcp.mcpb"
    with zipfile.ZipFile(bundle_path, "w") as bundle:
        bundle.write(ROOT / "manifest.json", "manifest.json")
        for name in ["README.md", "PRIVACY.md", "LICENSE", "logo.svg"]:
            bundle.writestr(name, "")
        bundle.writestr("bin/apple-ecosystem-mcp", "")
        bundle.writestr("bin/_internal/", "")
        bundle.writestr("bin/apple-ecosystem-helper", "")

    with zipfile.ZipFile(bundle_path) as bundle:
        validate_binary_bundle(bundle)


def test_uv_bundle_validator_accepts_expected_archive(tmp_path):
    bundle_path = tmp_path / "apple-ecosystem-mcp.mcpb"
    with zipfile.ZipFile(bundle_path, "w") as bundle:
        bundle.write(ROOT / "manifest.uv.json", "manifest.json")
        for name in ["README.md", "PRIVACY.md", "LICENSE", "logo.svg", "pyproject.toml", "uv.lock"]:
            bundle.writestr(name, "")
        bundle.writestr("bin/apple-ecosystem-helper", "")
        bundle.writestr("src/apple_ecosystem_mcp/__main__.py", "")

    with zipfile.ZipFile(bundle_path) as bundle:
        validate_uv_bundle(bundle)


def test_node_bundle_validator_accepts_expected_archive(tmp_path):
    bundle_path = tmp_path / "apple-ecosystem-mcp-node.mcpb"
    with zipfile.ZipFile(bundle_path, "w") as bundle:
        bundle.write(ROOT / "manifest.node.json", "manifest.json")
        for name in [
            "README.md",
            "PRIVACY.md",
            "LICENSE",
            "logo.svg",
            "package.json",
            "package-lock.json",
            "pyproject.toml",
            "uv.lock",
        ]:
            bundle.writestr(name, "")
        bundle.writestr("node_modules/", "")
        bundle.writestr("server/lib/fastmcp/", "")
        bundle.writestr("server/lib/mcp/", "")
        bundle.writestr("server/lib/pydantic_core/", "")
        bundle.writestr("server/node-launcher.mjs", "")
        bundle.writestr("server/runner.py", "")
        bundle.writestr("src/apple_ecosystem_mcp/__main__.py", "")
        bundle.writestr("bin/apple-ecosystem-helper", "")

    with zipfile.ZipFile(bundle_path) as bundle:
        validate_node_bundle(bundle)
