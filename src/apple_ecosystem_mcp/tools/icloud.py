from __future__ import annotations

import base64
import binascii
import os
import re
import subprocess
from pathlib import Path

from charset_normalizer import from_bytes
from mcp.types import ToolAnnotations

from ..permissions import ICLOUD_ROOT
from ..server import mcp

# Result-size policy per CLAUDE.md
_ICLOUD_READ_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_ICLOUD_SEARCH_MAX_RESULTS = 100
_ICLOUD_SEARCH_MAX_VISITED = 10_000


def _safe(user_path: str) -> Path:
    """Validate and resolve user-supplied iCloud path.

    User paths are relative to ICLOUD_ROOT. Strip leading slash, join relative
    to root, resolve, and verify no path traversal or symlink escape.
    """
    # Strip leading slash; treat as relative to ICLOUD_ROOT
    rel = Path(user_path.lstrip("/") or ".")

    # Reject .. segments
    if ".." in rel.parts:
        raise RuntimeError("Path escapes iCloud root")

    # Join relative to root and resolve symlinks
    resolved = (ICLOUD_ROOT / rel).resolve()

    # Verify resolved path is within ICLOUD_ROOT
    try:
        resolved.relative_to(ICLOUD_ROOT.resolve())
    except ValueError:
        raise RuntimeError("Path escapes iCloud root")

    return resolved


def _metadata(path: Path) -> dict:
    stat = path.stat()
    return {
        "name": path.name,
        "path": "/" + str(path.relative_to(ICLOUD_ROOT)),
        "size_bytes": stat.st_size,
        "modified": stat.st_mtime,
        "created": stat.st_ctime,
        "is_dir": path.is_dir(),
        "is_file": path.is_file(),
    }


def _validate_encoding(encoding: str) -> str:
    normalized = encoding.lower()
    if normalized not in {"auto", "utf-8", "base64"}:
        raise RuntimeError("encoding must be one of: auto, utf-8, base64")
    return normalized


def _walk_filename_search(target: Path, query: str) -> list[dict]:
    query_lower = query.lower()
    results = []
    visited = 0

    for root, dirs, files in _os_walk_sorted(target):
        names = list(dirs) + list(files)
        for name in names:
            visited += 1
            if visited > _ICLOUD_SEARCH_MAX_VISITED:
                return results

            if query_lower not in name.lower():
                continue

            item = root / name
            try:
                results.append(_metadata(item))
            except FileNotFoundError:
                continue

            if len(results) >= _ICLOUD_SEARCH_MAX_RESULTS:
                return results

    return results


def _os_walk_sorted(target: Path):
    for root, dirs, files in os.walk(target):
        dirs.sort()
        files.sort()
        yield Path(root), dirs, files


@mcp.tool(annotations=ToolAnnotations(title="List iCloud Files", readOnlyHint=True))
def icloud_list(path: str = "/") -> list[dict]:
    """List files and folders in iCloud Drive."""
    try:
        target = _safe(path)

        if not target.exists():
            raise RuntimeError(f"Path does not exist: {path}")

        if not target.is_dir():
            raise RuntimeError(f"Path is not a directory: {path}")

        result = []
        for item in sorted(target.iterdir()):
            metadata = _metadata(item)
            metadata["size"] = metadata["size_bytes"]
            result.append(metadata)
        return result
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to list iCloud path: {e}") from e


@mcp.tool(annotations=ToolAnnotations(title="Read iCloud File", readOnlyHint=True))
def icloud_read(path: str, encoding: str = "auto") -> dict:
    """Read a file from iCloud Drive."""
    try:
        encoding = _validate_encoding(encoding)
        target = _safe(path)

        if not target.exists():
            raise RuntimeError(f"File does not exist: {path}")

        if not target.is_file():
            raise RuntimeError(f"Path is not a file: {path}")

        # Check size limit
        size = target.stat().st_size
        if size > _ICLOUD_READ_MAX_BYTES:
            return {
                "error": f"File exceeds 10 MB limit",
                "size_bytes": size,
            }

        # Read raw bytes
        raw_bytes = target.read_bytes()

        if encoding == "base64":
            return {
                "path": "/" + str(target.relative_to(ICLOUD_ROOT)),
                "content": base64.b64encode(raw_bytes).decode("ascii"),
                "encoding": "base64",
                "size_bytes": size,
            }

        if encoding == "utf-8":
            return {
                "path": "/" + str(target.relative_to(ICLOUD_ROOT)),
                "content": raw_bytes.decode("utf-8"),
                "encoding": "utf-8",
                "size_bytes": size,
            }

        # Detect encoding with charset-normalizer
        detection = from_bytes(raw_bytes).best()
        encoding = detection.encoding if detection else "utf-8"

        try:
            content = raw_bytes.decode(encoding)
        except (UnicodeDecodeError, AttributeError):
            # Fallback to utf-8 with errors='replace'
            content = raw_bytes.decode("utf-8", errors="replace")
            encoding = "utf-8"

        return {
            "path": "/" + str(target.relative_to(ICLOUD_ROOT)),
            "content": content,
            "encoding": encoding,
            "size_bytes": size,
        }
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to read iCloud file: {e}") from e


@mcp.tool(annotations=ToolAnnotations(title="Write iCloud File", destructiveHint=True))
def icloud_write(
    path: str,
    content: str,
    create_dirs: bool = True,
    encoding: str = "utf-8",
) -> dict:
    """Write a file to iCloud Drive."""
    try:
        encoding = _validate_encoding(encoding)
        if encoding == "auto":
            raise RuntimeError("encoding='auto' is only supported for reads")

        target = _safe(path)

        # Create parent directories if requested
        if create_dirs:
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            # Ensure parent directory exists
            if not target.parent.exists():
                raise RuntimeError(f"Parent directory does not exist: {target.parent}")

        if encoding == "base64":
            try:
                target.write_bytes(base64.b64decode(content, validate=True))
            except (binascii.Error, ValueError) as e:
                raise RuntimeError("Invalid base64 content") from e
        else:
            target.write_text(content, encoding="utf-8")

        return {
            "path": "/" + str(target.relative_to(ICLOUD_ROOT)),
            "size_bytes": target.stat().st_size,
            "success": True,
        }
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to write iCloud file: {e}") from e


@mcp.tool(annotations=ToolAnnotations(title="Get iCloud File Metadata", readOnlyHint=True))
def icloud_stat(path: str) -> dict:
    """Return metadata for a file or folder in iCloud Drive."""
    try:
        target = _safe(path)

        if not target.exists():
            raise RuntimeError(f"Path does not exist: {path}")

        return _metadata(target)
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to stat iCloud path: {e}") from e


@mcp.tool(annotations=ToolAnnotations(title="Create iCloud Folder"))
def icloud_mkdir(path: str, parents: bool = True, exist_ok: bool = True) -> dict:
    """Create a folder in iCloud Drive."""
    try:
        target = _safe(path)
        target.mkdir(parents=parents, exist_ok=exist_ok)

        result = _metadata(target)
        result["success"] = True
        return result
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to create iCloud folder: {e}") from e


@mcp.tool(annotations=ToolAnnotations(title="Move iCloud File", destructiveHint=True))
def icloud_move(src: str, dst: str) -> dict:
    """Move or rename a file in iCloud Drive."""
    try:
        src_path = _safe(src)
        dst_path = _safe(dst)

        if not src_path.exists():
            raise RuntimeError(f"Source path does not exist: {src}")

        # Create destination parent directory if needed
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        # Move/rename the file
        src_path.rename(dst_path)

        return {
            "src": "/" + str(src_path.relative_to(ICLOUD_ROOT)),
            "dst": "/" + str(dst_path.relative_to(ICLOUD_ROOT)),
            "success": True,
        }
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to move iCloud file: {e}") from e


@mcp.tool(annotations=ToolAnnotations(title="Delete iCloud File", destructiveHint=True))
def icloud_delete(path: str, confirm: bool = False) -> dict:
    """Delete a file from iCloud Drive (requires confirm=True)."""
    try:
        target = _safe(path)

        if not target.exists():
            raise RuntimeError(f"Path does not exist: {path}")

        if not confirm:
            return {
                "preview": f"Would delete: {path}",
                "confirmed": False,
            }

        # Delete the file or directory
        if target.is_dir():
            import shutil
            shutil.rmtree(target)
        else:
            target.unlink()

        return {
            "path": "/" + str(target.relative_to(ICLOUD_ROOT)),
            "success": True,
        }
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to delete iCloud path: {e}") from e


@mcp.tool(annotations=ToolAnnotations(title="Search iCloud Drive", readOnlyHint=True))
def icloud_search(query: str, path: str = "/", content_search: bool = False) -> list[dict]:
    """Search iCloud Drive by filename or content."""
    try:
        # Validate query: reject shell metacharacters
        if re.search(r"[;&|`$()[\]{}<>\\'\"]", query):
            raise RuntimeError("Query contains unsafe shell metacharacters")

        target = _safe(path)

        if not target.exists():
            raise RuntimeError(f"Search path does not exist: {path}")

        if not target.is_dir():
            raise RuntimeError(f"Search path is not a directory: {path}")

        # Build mdfind command
        cmd = ["mdfind", "-onlyin", str(target)]
        if content_search:
            cmd.append("-interpret")
        cmd.append(query)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        if result.returncode != 0 and result.returncode != 1:
            raise RuntimeError(f"mdfind failed with exit code {result.returncode}")

        results_by_path = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            try:
                file_path = Path(line)
                if file_path.exists():
                    metadata = _metadata(file_path)
                    results_by_path[metadata["path"]] = metadata
            except (ValueError, FileNotFoundError):
                # Skip paths that don't exist or can't be resolved
                continue

        if not content_search and len(results_by_path) < _ICLOUD_SEARCH_MAX_RESULTS:
            walk_results = _walk_filename_search(target, query)
            for item in walk_results:
                results_by_path.setdefault(item["path"], item)
                if len(results_by_path) >= _ICLOUD_SEARCH_MAX_RESULTS:
                    break

        return [
            results_by_path[path]
            for path in sorted(results_by_path)
        ][: _ICLOUD_SEARCH_MAX_RESULTS]
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to search iCloud: {e}") from e


__all__ = ["ICLOUD_ROOT"]
