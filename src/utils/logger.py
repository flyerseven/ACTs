import logging
import sys
from datetime import datetime
from pathlib import Path


LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"


class Tee:
    """Duplicates writes to a file and the original stream."""

    def __init__(self, filepath: Path, stream):
        self.file = open(filepath, "w", encoding="utf-8", buffering=1)
        self.stream = stream

    def write(self, data):
        self.file.write(data)
        self.stream.write(data)

    def flush(self):
        self.file.flush()
        self.stream.flush()

    def close(self):
        self.file.close()


def setup_logging(level: int = logging.INFO, log_dir: Path | None = None) -> Path:
    if log_dir is None:
        log_dir = Path.cwd() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"acts_{timestamp}.log"

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)

    sys.stdout = Tee(log_path, sys.__stdout__)  # type: ignore[assignment]
    sys.stderr = Tee(log_path, sys.__stderr__)  # type: ignore[assignment]

    return log_path
