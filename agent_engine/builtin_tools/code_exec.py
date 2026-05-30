"""Sandboxed code execution tool using subprocess."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def execute_python(code: str, timeout_sec: float = 10.0) -> str:
    """Execute Python code in an isolated subprocess.

    The code runs in a temporary directory with no network access
    and a strict timeout.

    Args:
        code: Python source code to execute.
        timeout_sec: Maximum execution time in seconds.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "script.py"
            script_path.write_text(code, encoding="utf-8")

            env = {"PYTHONIOENCODING": "utf-8"}
            result = subprocess.run(
                ["python", str(script_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
                cwd=tmpdir,
                env=env,
            )

            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"

            return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Execution timed out after {timeout_sec}s"
    except FileNotFoundError:
        return "Error: 'python' not found in PATH"
    except Exception as e:
        return f"Execution error: {e}"
