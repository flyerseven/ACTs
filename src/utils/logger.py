"""Centralized logging setup with loguru.

Configures dual sinks:
- Console (stderr): concise colored output, default INFO level
- File: structured detailed output with rotation, default DEBUG level

The ``Tee`` class captures stdout (user-facing print output) to the log
file while preserving it on screen.  stderr is handled exclusively by
loguru — no stderr Tee.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger as _loguru_logger

# ── Tee (stdout only, for user-facing print output) ──────────────

class Tee:
    """Duplicates writes to a file and the original stdout stream."""

    def __init__(self, filepath: Path, stream):
        self.file = open(filepath, "a", encoding="utf-8", buffering=1)
        self.stream = stream

    def write(self, data):
        self.file.write(data)
        self.stream.write(data)

    def flush(self):
        self.file.flush()
        self.stream.flush()

    def close(self):
        self.file.close()


# ── Public API ───────────────────────────────────────────────────

def setup_logging(
    log_dir: Path | None = None,
    console_level: str = "INFO",
    file_level: str = "DEBUG",
) -> Path:
    """Configure loguru and return the log file path.

    Args:
        log_dir: Directory for log files (default: ``./logs``).
        console_level: Minimum level for the stderr console sink.
        file_level: Minimum level for the rotating file sink.

    Returns the path to the current log file.

    After calling this, stdout is tee'd to the log file.  stderr is
    managed exclusively by loguru (no tee).
    """
    if log_dir is None:
        log_dir = Path.cwd() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"acts_{timestamp}.log"

    # Ensure TRACE level exists (below DEBUG)
    _register_trace_level()

    # Remove all prior handlers (both loguru and any leftover from
    # previous calls).
    _loguru_logger.remove()

    # ── Console sink (stderr): concise, colored ──
    _loguru_logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=console_level,
        colorize=True,
    )

    # ── File sink: structured, detailed, with rotation ──
    _loguru_logger.add(
        str(log_path),
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        level=file_level,
        rotation="10 MB",
        retention=5,
        encoding="utf-8",
    )

    # Bridge stdlib logging → loguru for third-party libraries
    _setup_stdlib_bridge()

    # Tee stdout to the log file (user-facing print() output).
    # Do NOT tee stderr — loguru owns stderr directly.
    sys.stdout = Tee(log_path, sys.__stdout__)  # type: ignore[assignment]

    return log_path


def update_loguru_levels(console_level: str, file_level: str) -> None:
    """Update console and file sink levels at runtime."""
    for handler_id, handler_config in list(_loguru_logger._core.handlers.items()):
        sink = handler_config._sink  # type: ignore[union-attr]
        # Identify sink by type/name
        if isinstance(sink, str) and sink.endswith(".log"):
            # File sink
            _loguru_logger.configure(handlers=[{"id": handler_id, "level": file_level}])
        elif getattr(sink, "stream", None) is sys.stderr or getattr(sink, "name", "") == "<stderr>":
            # Console sink
            _loguru_logger.configure(handlers=[{"id": handler_id, "level": console_level}])


# ── Internal helpers ─────────────────────────────────────────────

def _register_trace_level() -> None:
    """Register a custom TRACE level (no=5, below DEBUG which is 10)."""
    try:
        _loguru_logger.level("TRACE", no=5, color="<dim>")
    except (ValueError, TypeError):
        pass  # already registered


def _setup_stdlib_bridge() -> None:
    """Redirect stdlib ``logging`` messages to loguru."""
    class _LoguruHandler(logging.Handler):
        def emit(self, record):
            try:
                level = _loguru_logger.level(record.levelname).name
            except (ValueError, KeyError):
                level = record.levelno
            frame = logging.currentframe()
            depth = 2
            while frame and frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1
            _loguru_logger.opt(depth=depth, exception=record.exc_info).log(
                level, record.getMessage()
            )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(_LoguruHandler())
    root.setLevel(logging.DEBUG)
