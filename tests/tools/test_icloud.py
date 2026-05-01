import base64
from unittest.mock import MagicMock, patch

import pytest

from apple_ecosystem_mcp.tools import icloud  # noqa: F401
from apple_ecosystem_mcp.tools.icloud import (
    _safe,
    icloud_delete,
    icloud_list,
    icloud_mkdir,
    icloud_move,
    icloud_read,
    icloud_search,
    icloud_stat,
    icloud_write,
)
from apple_ecosystem_mcp.permissions import ICLOUD_ROOT


class TestSafePathHelper:
    """Test the _safe() path validation helper."""

    def test_safe_resolves_relative_path(self, tmp_path):
        """User path "/" should resolve to ICLOUD_ROOT."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            result = _safe("/")
            assert result == tmp_path.resolve()

    def test_safe_strips_leading_slash(self, tmp_path):
        """Leading slash is stripped and path treated as relative."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "test.txt").touch()
            result = _safe("/test.txt")
            assert result == tmp_path / "test.txt"

    def test_safe_rejects_path_traversal_with_dotdot(self, tmp_path):
        """Paths containing '..' are rejected."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            with pytest.raises(RuntimeError, match="escapes iCloud root"):
                _safe("/../etc/passwd")

    def test_safe_rejects_symlink_escape(self, tmp_path):
        """Symlinks resolving outside ICLOUD_ROOT are rejected."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            external_dir = tmp_path.parent / "outside"
            external_dir.mkdir(exist_ok=True)
            link_path = tmp_path / "link"
            try:
                link_path.symlink_to(external_dir)
            except (OSError, NotImplementedError):
                # Skip on systems that don't support symlinks (e.g. Windows)
                pytest.skip("Symlinks not supported")

            with pytest.raises(RuntimeError, match="escapes iCloud root"):
                _safe("/link")

    def test_safe_accepts_nested_paths(self, tmp_path):
        """Nested paths within ICLOUD_ROOT are accepted."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "a" / "b" / "c").mkdir(parents=True)
            result = _safe("/a/b/c")
            assert result == tmp_path / "a" / "b" / "c"

    def test_safe_handles_empty_path(self, tmp_path):
        """Empty path defaults to root."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            result = _safe("")
            assert result == tmp_path


class TestIcloudList:
    """Test icloud_list tool."""

    def test_icloud_list_root(self, tmp_path):
        """Listing root returns all items."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "file1.txt").touch()
            (tmp_path / "folder1").mkdir()

            result = icloud_list("/")

            assert len(result) == 2
            assert any(item["name"] == "file1.txt" for item in result)
            assert any(item["name"] == "folder1" for item in result)
            assert any(item["is_dir"] is False for item in result)
            assert any(item["is_dir"] is True for item in result)

    def test_icloud_list_includes_metadata(self, tmp_path):
        """Listed items include size, modified time, and path."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "test.txt").write_text("content")

            result = icloud_list("/")

            item = result[0]
            assert "name" in item
            assert "path" in item
            assert "size" in item
            assert "modified" in item
            assert "is_dir" in item
            assert item["size"] == len(b"content")

    def test_icloud_list_nested_directory(self, tmp_path):
        """Listing a subdirectory returns only its contents."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "subdir").mkdir()
            (tmp_path / "subdir" / "file.txt").touch()
            (tmp_path / "other.txt").touch()

            result = icloud_list("/subdir")

            assert len(result) == 1
            assert result[0]["name"] == "file.txt"

    def test_icloud_list_nonexistent_path(self, tmp_path):
        """Listing a nonexistent path raises RuntimeError."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            with pytest.raises(RuntimeError, match="does not exist"):
                icloud_list("/nonexistent")

    def test_icloud_list_file_as_directory(self, tmp_path):
        """Listing a file raises RuntimeError."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "file.txt").touch()

            with pytest.raises(RuntimeError, match="not a directory"):
                icloud_list("/file.txt")


class TestIcloudRead:
    """Test icloud_read tool."""

    def test_icloud_read_text_file(self, tmp_path):
        """Reading a text file returns content."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            content = "Hello, iCloud!"
            (tmp_path / "test.txt").write_text(content)

            result = icloud_read("/test.txt")

            assert result["content"] == content
            assert result["path"] == "/test.txt"
            assert result["size_bytes"] == len(content.encode("utf-8"))

    def test_icloud_read_detects_encoding(self, tmp_path):
        """Reading detects file encoding."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "test.txt").write_text("UTF-8 content", encoding="utf-8")

            result = icloud_read("/test.txt")

            assert "encoding" in result
            assert result["encoding"] is not None

    def test_icloud_read_truncates_large_content(self, tmp_path):
        """Reading a file over 10 MB returns error dict."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            # Create a file larger than 10 MB
            large_file = tmp_path / "large.bin"
            with open(large_file, "wb") as f:
                f.write(b"x" * (11 * 1024 * 1024))

            result = icloud_read("/large.bin")

            assert "error" in result
            assert "size_bytes" in result
            assert result["size_bytes"] > 10 * 1024 * 1024
            assert "content" not in result

    def test_icloud_read_nonexistent_file(self, tmp_path):
        """Reading a nonexistent file raises RuntimeError."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            with pytest.raises(RuntimeError, match="does not exist"):
                icloud_read("/nonexistent.txt")

    def test_icloud_read_directory_as_file(self, tmp_path):
        """Reading a directory raises RuntimeError."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "subdir").mkdir()

            with pytest.raises(RuntimeError, match="not a file"):
                icloud_read("/subdir")

    def test_icloud_read_base64_binary_file(self, tmp_path):
        """Reading with encoding=base64 returns binary-safe content."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            raw = b"\x00\xffbinary\x80"
            (tmp_path / "data.bin").write_bytes(raw)

            result = icloud_read("/data.bin", encoding="base64")

            assert result["content"] == base64.b64encode(raw).decode("ascii")
            assert result["encoding"] == "base64"


class TestIcloudWrite:
    """Test icloud_write tool."""

    def test_icloud_write_creates_file(self, tmp_path):
        """Writing creates a file with content."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            content = "Test content"

            result = icloud_write("/test.txt", content)

            assert result["success"] is True
            assert result["path"] == "/test.txt"
            assert (tmp_path / "test.txt").read_text() == content

    def test_icloud_write_creates_parent_directories(self, tmp_path):
        """Writing with create_dirs=True creates missing parent dirs."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            result = icloud_write("/a/b/c/file.txt", "content", create_dirs=True)

            assert result["success"] is True
            assert (tmp_path / "a" / "b" / "c" / "file.txt").exists()

    def test_icloud_write_without_create_dirs_fails(self, tmp_path):
        """Writing with create_dirs=False fails if parent doesn't exist."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            with pytest.raises(RuntimeError, match="Parent directory does not exist"):
                icloud_write("/nonexistent/file.txt", "content", create_dirs=False)

    def test_icloud_write_overwrites_existing(self, tmp_path):
        """Writing to existing file overwrites it."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "test.txt").write_text("old")

            icloud_write("/test.txt", "new")

            assert (tmp_path / "test.txt").read_text() == "new"

    def test_icloud_write_base64_binary_file(self, tmp_path):
        """Writing with encoding=base64 decodes binary content."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            raw = b"\x00\xffbinary\x80"
            encoded = base64.b64encode(raw).decode("ascii")

            result = icloud_write("/data.bin", encoded, encoding="base64")

            assert result["success"] is True
            assert (tmp_path / "data.bin").read_bytes() == raw

    def test_icloud_write_rejects_invalid_base64(self, tmp_path):
        """Invalid base64 content raises RuntimeError."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            with pytest.raises(RuntimeError, match="Invalid base64"):
                icloud_write("/data.bin", "not valid base64", encoding="base64")


class TestIcloudStat:
    """Test icloud_stat tool."""

    def test_icloud_stat_file_metadata(self, tmp_path):
        """Stat returns file metadata."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "file.txt").write_text("content")

            result = icloud_stat("/file.txt")

            assert result["name"] == "file.txt"
            assert result["path"] == "/file.txt"
            assert result["size_bytes"] == len(b"content")
            assert result["is_file"] is True
            assert result["is_dir"] is False
            assert "modified" in result
            assert "created" in result

    def test_icloud_stat_directory_metadata(self, tmp_path):
        """Stat returns directory metadata."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "folder").mkdir()

            result = icloud_stat("/folder")

            assert result["name"] == "folder"
            assert result["is_dir"] is True
            assert result["is_file"] is False

    def test_icloud_stat_nonexistent_path(self, tmp_path):
        """Stat on nonexistent path raises RuntimeError."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            with pytest.raises(RuntimeError, match="does not exist"):
                icloud_stat("/missing")


class TestIcloudMkdir:
    """Test icloud_mkdir tool."""

    def test_icloud_mkdir_creates_directory(self, tmp_path):
        """Mkdir creates a directory and returns metadata."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            result = icloud_mkdir("/folder")

            assert result["success"] is True
            assert result["path"] == "/folder"
            assert result["is_dir"] is True
            assert (tmp_path / "folder").is_dir()

    def test_icloud_mkdir_creates_parent_directories(self, tmp_path):
        """Mkdir creates parent directories by default."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            result = icloud_mkdir("/a/b/c")

            assert result["success"] is True
            assert (tmp_path / "a" / "b" / "c").is_dir()

    def test_icloud_mkdir_without_parents_fails(self, tmp_path):
        """Mkdir with parents=False fails if the parent is missing."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            with pytest.raises(RuntimeError, match="Failed to create"):
                icloud_mkdir("/a/b/c", parents=False)


class TestIcloudMove:
    """Test icloud_move tool."""

    def test_icloud_move_renames_file(self, tmp_path):
        """Moving renames a file."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "old.txt").write_text("content")

            result = icloud_move("/old.txt", "/new.txt")

            assert result["success"] is True
            assert (tmp_path / "new.txt").exists()
            assert not (tmp_path / "old.txt").exists()

    def test_icloud_move_to_subdirectory(self, tmp_path):
        """Moving to a subdirectory works."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "file.txt").write_text("content")
            (tmp_path / "subdir").mkdir()

            result = icloud_move("/file.txt", "/subdir/file.txt")

            assert result["success"] is True
            assert (tmp_path / "subdir" / "file.txt").exists()

    def test_icloud_move_nonexistent_source(self, tmp_path):
        """Moving a nonexistent file raises RuntimeError."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            with pytest.raises(RuntimeError, match="does not exist"):
                icloud_move("/nonexistent.txt", "/dest.txt")

    def test_icloud_move_creates_dest_parent(self, tmp_path):
        """Moving creates parent directory if needed."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "file.txt").write_text("content")

            icloud_move("/file.txt", "/a/b/c/file.txt")

            assert (tmp_path / "a" / "b" / "c" / "file.txt").exists()


class TestIcloudDelete:
    """Test icloud_delete tool."""

    def test_icloud_delete_dry_run_by_default(self, tmp_path):
        """Delete without confirm=True returns preview."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "file.txt").touch()

            result = icloud_delete("/file.txt", confirm=False)

            assert result["confirmed"] is False
            assert "preview" in result
            assert (tmp_path / "file.txt").exists()  # Not deleted

    def test_icloud_delete_with_confirm(self, tmp_path):
        """Delete with confirm=True deletes the file."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "file.txt").touch()

            result = icloud_delete("/file.txt", confirm=True)

            assert result["success"] is True
            assert not (tmp_path / "file.txt").exists()

    def test_icloud_delete_directory(self, tmp_path):
        """Delete removes directories recursively."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "subdir").mkdir()
            (tmp_path / "subdir" / "file.txt").touch()

            result = icloud_delete("/subdir", confirm=True)

            assert result["success"] is True
            assert not (tmp_path / "subdir").exists()

    def test_icloud_delete_nonexistent(self, tmp_path):
        """Deleting a nonexistent path raises RuntimeError."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            with pytest.raises(RuntimeError, match="does not exist"):
                icloud_delete("/nonexistent.txt", confirm=True)


class TestIcloudSearch:
    """Test icloud_search tool."""

    def test_icloud_search_by_filename(self, tmp_path):
        """Searching finds files by name."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "test.txt").touch()
            (tmp_path / "other.py").touch()

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout=str(tmp_path / "test.txt"),
                )
                result = icloud_search("test")

                assert len(result) == 1
                assert result[0]["name"] == "test.txt"

    def test_icloud_search_with_content_flag(self, tmp_path):
        """Searching with content_search=True passes -interpret flag."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="")
                icloud_search("query", "/", content_search=True)

                # Check that -interpret was passed
                call_args = mock_run.call_args[0][0]
                assert "-interpret" in call_args

    def test_icloud_search_rejects_shell_metacharacters(self, tmp_path):
        """Searching with shell metacharacters raises RuntimeError."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            with pytest.raises(RuntimeError, match="unsafe"):
                icloud_search("test'; rm -rf /")

    def test_icloud_search_rejects_piping(self, tmp_path):
        """Searching rejects pipe and other shell operators."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            with pytest.raises(RuntimeError, match="unsafe"):
                icloud_search("test | cat")

    def test_icloud_search_nonexistent_path(self, tmp_path):
        """Searching in nonexistent path raises RuntimeError."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            with pytest.raises(RuntimeError, match="does not exist"):
                icloud_search("query", "/nonexistent")

    def test_icloud_search_file_as_directory(self, tmp_path):
        """Searching in a file raises RuntimeError."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "file.txt").touch()

            with pytest.raises(RuntimeError, match="not a directory"):
                icloud_search("query", "/file.txt")

    def test_icloud_search_empty_results(self, tmp_path):
        """Searching with no results returns empty list."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="")
                result = icloud_search("nonexistent")

                assert result == []

    def test_icloud_search_walk_finds_spotlight_miss(self, tmp_path):
        """Filename search falls back to deterministic os.walk matching."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "b").mkdir()
            (tmp_path / "a").mkdir()
            (tmp_path / "b" / "needle.txt").touch()
            (tmp_path / "a" / "needle.txt").touch()

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="")
                result = icloud_search("needle")

            assert [item["path"] for item in result] == [
                "/a/needle.txt",
                "/b/needle.txt",
            ]

    def test_icloud_search_walk_respects_result_cap(self, tmp_path):
        """Filename search caps local walk results."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            for index in range(3):
                (tmp_path / f"needle-{index}.txt").touch()

            with (
                patch("apple_ecosystem_mcp.tools.icloud._ICLOUD_SEARCH_MAX_RESULTS", 2),
                patch("subprocess.run") as mock_run,
            ):
                mock_run.return_value = MagicMock(returncode=0, stdout="")
                result = icloud_search("needle")

            assert len(result) == 2
            assert [item["path"] for item in result] == [
                "/needle-0.txt",
                "/needle-1.txt",
            ]

    def test_icloud_search_walk_respects_visit_cap(self, tmp_path):
        """Filename search stops walking after the visit cap."""
        with patch("apple_ecosystem_mcp.tools.icloud.ICLOUD_ROOT", tmp_path):
            (tmp_path / "alpha.txt").touch()
            (tmp_path / "needle.txt").touch()

            with (
                patch("apple_ecosystem_mcp.tools.icloud._ICLOUD_SEARCH_MAX_VISITED", 1),
                patch("subprocess.run") as mock_run,
            ):
                mock_run.return_value = MagicMock(returncode=0, stdout="")
                result = icloud_search("needle")

            assert result == []
