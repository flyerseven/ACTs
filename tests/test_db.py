import asyncio
from pathlib import Path

from storage.db import init_db


def test_init_db(tmp_path: Path) -> None:
    db_path = tmp_path / "Acts" / "index.db"
    asyncio.run(init_db(db_path))
    assert db_path.exists()
