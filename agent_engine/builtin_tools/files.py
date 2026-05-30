"""Sandboxed file I/O tools.

- ``read_file`` and ``list_files``: read-only access to the entire filesystem.
  Absolute paths (e.g. ``D:\\data\\file.txt``, ``/home/user/file.txt``) bypass
  the workspace sandbox and can read any file the process has permission to access.
  Relative paths are resolved within the workspace.
- ``write_file``: workspace-sandboxed for relative paths.  Absolute paths are
  allowed on any drive EXCEPT C: (e.g. ``D:\\data\\out.txt``, ``E:\\projects\\f.py``
  are OK; ``C:\\Windows\\...`` is rejected).  C: drive protection cannot be
  bypassed.
"""
from __future__ import annotations

from pathlib import Path


_DEFAULT_WORKSPACE = Path("./workspace").resolve()


def _is_absolute_path(filepath: str) -> bool:
    """Check if a path string looks absolute — cross-platform safe check
    that doesn't require the path to exist."""
    # Windows absolute: C:\, D:\, \\server\share
    # Unix absolute: /...
    return Path(filepath).is_absolute()


def _is_c_drive(filepath: str) -> bool:
    """Check if an absolute path is on the protected C: drive."""
    import platform
    if platform.system() != "Windows":
        return False
    # Normalize separators and check for C: prefix (case-insensitive).
    # Also handles /c/... (Git Bash / MSYS2 style).
    p = filepath.replace("\\", "/").lower()
    if p.startswith("c:") or p.startswith("/c/"):
        return True
    return False


def _resolve_safe(workspace: Path, filepath: str) -> Path:
    """Resolve a relative file path, ensuring it stays within workspace.
    Raises ValueError on path traversal attempts."""
    workspace = workspace.resolve()
    target = (workspace / filepath).resolve()
    if not str(target).startswith(str(workspace)):
        raise ValueError(f"Path traversal detected: {filepath}")
    return target


# ── Read-only tools (full filesystem access) ─────────────────────────────

def read_file(filepath: str, offset: int = 1, limit: int = 0,
              workspace_dir: str = "") -> str:
    """Read the contents of a file, with optional line-range pagination.

    Supports two modes:
    - **Absolute path** (e.g. ``D:\\data\\file.txt``, ``/etc/hosts``):
      reads directly from that path — full filesystem access.
    - **Relative path** (e.g. ``src/main.py``, ``config.yaml``):
      resolved within the workspace directory.

    For large files, use ``offset`` and ``limit`` to read a slice of lines
    (1-based).  When ``limit`` is 0 (the default), the entire file is
    returned.  The returned text is always prefixed with a status header
    like ``[Lines 1-50 / 300]`` so the caller knows where they are.

    Args:
        filepath: Absolute or relative path to the file.
        offset: First line to read (1-based, default 1).
        limit: Maximum number of lines to return (0 = read to end).
        workspace_dir: Optional workspace root (defaults to ./workspace).
    """
    ws = Path(workspace_dir).resolve() if workspace_dir else _DEFAULT_WORKSPACE
    try:
        if _is_absolute_path(filepath):
            target = Path(filepath).resolve()
        else:
            target = _resolve_safe(ws, filepath)
        if not target.exists():
            return f"File not found: {filepath}"
        if not target.is_file():
            return f"Not a file: {filepath}"

        raw = target.read_text(encoding="utf-8", errors="replace")
        lines = raw.splitlines()
        total = len(lines)

        # Normalise range
        start = max(1, offset) - 1          # → 0-based
        if start >= total:
            return f"[Lines {start + 1}-? / {total}] (offset past end of file)"

        if limit > 0:
            end = min(start + limit, total)
        else:
            end = total

        chunk = lines[start:end]
        body = "\n".join(chunk)

        # Build a compact status header
        if limit > 0 and end < total:
            header = f"[Lines {start + 1}-{end} / {total} — use offset={end + 1} for next page]\n"
        elif start == 0 and end == total:
            header = f"[Full file — {total} lines, {len(raw)} chars]\n"
        else:
            header = f"[Lines {start + 1}-{end} / {total}]\n"

        return header + body
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Read error: {e}"


def list_files(directory: str = ".", workspace_dir: str = "") -> str:
    """List files in a directory.

    Supports two modes:
    - **Absolute path** (e.g. ``D:\\projects``, ``/var/log``):
      lists that directory directly — full filesystem access.
    - **Relative path** (e.g. ``src``, ``.``):
      resolved within the workspace directory.

    Args:
        directory: Absolute or relative directory path (default: workspace root).
        workspace_dir: Optional workspace root.
    """
    ws = Path(workspace_dir).resolve() if workspace_dir else _DEFAULT_WORKSPACE
    try:
        if _is_absolute_path(directory):
            target = Path(directory).resolve()
        else:
            target = _resolve_safe(ws, directory)
        if not target.exists():
            return f"Directory not found: {directory}"
        if not target.is_dir():
            return f"Not a directory: {directory}"
        items = sorted(target.iterdir())
        lines = []
        for item in items:
            if item.is_dir():
                lines.append(f"[DIR] {item.name}")
            else:
                size = item.stat().st_size
                lines.append(f"[FILE] {item.name} ({size}B)")
        return "\n".join(lines) if lines else "(empty)"
    except Exception as e:
        return f"Error: {e}"


# ── Write tool (workspace-sandboxed) ────────────────────────────────────

def write_file(filepath: str, content: str, workspace_dir: str = "") -> str:
    """Write content to a file.

    Three-path dispatch:

    1. **Relative path** (e.g. ``src/main.py``, ``output/result.json``):
       resolved within the workspace — sandboxed, no traversal.
    2. **Absolute path on C: drive** (``C:\\...``, ``/c/...``):
       REJECTED — protected system drive.
    3. **Absolute path on any other drive** (``D:\\...``, ``E:\\...``,
       ``/d/...``, ``/home/...`` on Linux): allowed — writes directly
       to that path.

    Args:
        filepath: Relative or absolute path to write to.
        content: Text content to write.
        workspace_dir: Optional workspace root (defaults to ./workspace).
    """
    ws = Path(workspace_dir).resolve() if workspace_dir else _DEFAULT_WORKSPACE
    try:
        # ── C: drive protection — checked FIRST, before any path resolution ──
        if _is_c_drive(filepath):
            return (
                "Error: C: drive is protected.  write_file cannot modify files "
                "on the C: drive.  Please save to a different drive (D:, E:, "
                "etc.) or use a relative path for the workspace."
            )

        if _is_absolute_path(filepath):
            # Non-C absolute path — allowed, write directly.
            target = Path(filepath).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Written {len(content)} bytes to {filepath}"
        # Relative path — workspace-sandboxed.
        target = _resolve_safe(ws, filepath)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Written {len(content)} bytes to {filepath}"
    except ValueError as e:
        return f"Error: {e}"
    except PermissionError as e:
        return f"Error: Permission denied — {e}"
    except Exception as e:
        return f"Write error: {e}"


def replace_in_file(filepath: str, old_string: str, new_string: str,
                    replace_all: bool = False, workspace_dir: str = "") -> str:
    """Replace text in a file by exact string matching.

    Reads the file at ``filepath``, finds ``old_string``, and replaces it with
    ``new_string``.  This avoids the need to send the full file content as a
    tool call argument — only the specific text to change is needed.

    Path rules are the same as ``write_file``: C: drive is protected; non-C
    absolute paths (D:\\\\, E:\\\\, /home/...) and relative paths are allowed.

    Args:
        filepath: Absolute or relative path to the file.
        old_string: Exact text to find and replace.
        new_string: Replacement text.
        replace_all: If True, replace every occurrence of old_string.
                     If False (the default), replace only the first match.
        workspace_dir: Optional workspace root (defaults to ./workspace).

    Returns:
        A status message reporting success, or an error message.
    """
    ws = Path(workspace_dir).resolve() if workspace_dir else _DEFAULT_WORKSPACE
    try:
        # ── C: drive protection ──
        if _is_c_drive(filepath):
            return (
                "Error: C: drive is protected.  replace_in_file cannot modify "
                "files on the C: drive.  Please save to a different drive "
                "(D:, E:, etc.) or use a relative path for the workspace."
            )

        # ── Resolve target path ──
        if _is_absolute_path(filepath):
            target = Path(filepath).resolve()
        else:
            target = _resolve_safe(ws, filepath)

        if not target.exists():
            return f"Error: File not found: {filepath}"
        if not target.is_file():
            return f"Error: Not a file: {filepath}"

        raw = target.read_text(encoding="utf-8", errors="replace")

        # ── Find and replace ──
        count = raw.count(old_string)
        if count == 0:
            return (
                f"Error: old_string not found in {filepath}. "
                f"Make sure the text matches exactly (whitespace, indentation, "
                f"newlines are significant)."
            )

        if not replace_all and count > 1:
            return (
                f"Error: old_string appears {count} times in {filepath}. "
                f"Use replace_all=True to replace all occurrences, or include "
                f"more surrounding context in old_string to make it unique."
            )

        new_raw = raw.replace(old_string, new_string) if replace_all else raw.replace(old_string, new_string, 1)

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_raw, encoding="utf-8")

        action = f"{count} occurrence(s)" if replace_all else "1 occurrence"
        return (
            f"Replaced {action} in {filepath}. "
            f"File size: {len(new_raw)} chars ({len(raw)} → {len(new_raw)})."
        )
    except ValueError as e:
        return f"Error: {e}"
    except PermissionError as e:
        return f"Error: Permission denied — {e}"
    except Exception as e:
        return f"Replace error: {e}"
