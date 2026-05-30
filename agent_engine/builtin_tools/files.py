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
    """Resolve a relative file path, ensuring it stays within workspace.
    Raises ValueError on path traversal attempts."""
    workspace = workspace.resolve()
    target = (workspace / filepath).resolve()
    if not str(target).startswith(str(workspace)):
        raise ValueError(f"Path traversal detected: {filepath}")
    return target


# ── Read-only tools (full filesystem access) ─────────────────────────────

# ── Read-only tools (full filesystem access) ─────────────────────────────

def read_file(filepath: str, workspace_dir: str = "") -> str:
    """Read the contents of a file.

    Supports two modes:
    - **Absolute path** (e.g. ``D:\\data\\file.txt``, ``/etc/hosts``):
      reads directly from that path — full filesystem access.
    - **Relative path** (e.g. ``src/main.py``, ``config.yaml``):
      resolved within the workspace directory.
    """Read the contents of a file.

    Supports two modes:
    - **Absolute path** (e.g. ``D:\\data\\file.txt``, ``/etc/hosts``):
      reads directly from that path — full filesystem access.
    - **Relative path** (e.g. ``src/main.py``, ``config.yaml``):
      resolved within the workspace directory.

    Args:
        filepath: Absolute or relative path to the file.
        filepath: Absolute or relative path to the file.
        workspace_dir: Optional workspace root (defaults to ./workspace).
    """
    ws = Path(workspace_dir).resolve() if workspace_dir else _DEFAULT_WORKSPACE
    try:
        if _is_absolute_path(filepath):
            target = Path(filepath).resolve()
        else:
            target = _resolve_safe(ws, filepath)
        if _is_absolute_path(filepath):
            target = Path(filepath).resolve()
        else:
            target = _resolve_safe(ws, filepath)
        if not target.exists():
            return f"File not found: {filepath}"
        if not target.is_file():
            return f"Not a file: {filepath}"
        return target.read_text(encoding="utf-8", errors="replace")
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
    """List files in a directory.

    Supports two modes:
    - **Absolute path** (e.g. ``D:\\projects``, ``/var/log``):
      lists that directory directly — full filesystem access.
    - **Relative path** (e.g. ``src``, ``.``):
      resolved within the workspace directory.

    Args:
        directory: Absolute or relative directory path (default: workspace root).
        directory: Absolute or relative directory path (default: workspace root).
        workspace_dir: Optional workspace root.
    """
    ws = Path(workspace_dir).resolve() if workspace_dir else _DEFAULT_WORKSPACE
    try:
        if _is_absolute_path(directory):
            target = Path(directory).resolve()
        else:
            target = _resolve_safe(ws, directory)
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
