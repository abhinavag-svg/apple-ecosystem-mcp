#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
import sysconfig
from pathlib import Path


SKIP_NAMES = {
    "__pycache__",
    "apple_ecosystem_mcp",
}


def should_skip(path: Path) -> bool:
    name = path.name
    return (
        name in SKIP_NAMES
        or name.endswith(".pyc")
        or name.endswith(".pyo")
        or name == "direct_url.json"
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: vendor_python_deps.py DEST", file=sys.stderr)
        return 2

    source = Path(sysconfig.get_paths()["platlib"])
    dest = Path(args[0])
    if not source.exists():
        print(f"site-packages not found: {source}", file=sys.stderr)
        return 1

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    for child in source.iterdir():
        if should_skip(child):
            continue
        target = dest / child.name
        if child.is_dir():
            shutil.copytree(child, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        else:
            shutil.copy2(child, target)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
