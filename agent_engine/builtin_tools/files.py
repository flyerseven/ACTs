"""Sandboxed file I/O tools."""
from __future__ import annotations

from pathlib import Path


_DEFAULT_WORKSPACE = Path("./workspace").resolve()


def _resolve_safe(workspace: Path, filepath: str) -> Path:
    """Resolve a file path, ensuring it stays within workspace."""
    workspace = workspace.resolve()
    target = (workspace / filepath).resolve()
    if not str(target).startswith(str(workspace)):
        raise ValueError(f"Path traversal detected: {filepath}")
    return target


def read_file(filepath: str, workspace_dir: str = "") -> str:
    """Read the contents of a file within the workspace.

    Args:
        filepath: Relative path to the file within the workspace.
        workspace_dir: Optional workspace root (defaults to ./workspace).
    """
    ws = Path(workspace_dir).resolve() if workspace_dir else _DEFAULT_WORKSPACE
    try:
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


def write_file(filepath: str, content: str, workspace_dir: str = "") -> str:
    """Write content to a file within the workspace.

    Args:
        filepath: Relative path within the workspace.
        content: Text content to write.
        workspace_dir: Optional workspace root (defaults to ./workspace).
    """
    ws = Path(workspace_dir).resolve() if workspace_dir else _DEFAULT_WORKSPACE
    try:
        target = _resolve_safe(ws, filepath)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Written {len(content)} bytes to {filepath}"
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Write error: {e}"


def list_files(directory: str = ".", workspace_dir: str = "") -> str:
    """List files in a workspace directory.

    Args:
        directory: Relative directory path (default: workspace root).
        workspace_dir: Optional workspace root.
    """
    ws = Path(workspace_dir).resolve() if workspace_dir else _DEFAULT_WORKSPACE
    try:
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
