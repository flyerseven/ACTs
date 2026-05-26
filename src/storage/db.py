from __future__ import annotations

from pathlib import Path

import aiosqlite


CREATE_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        model_provider TEXT,
        model_name TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        target_type TEXT,
        target_id TEXT,
        status TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """,
]


async def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        for stmt in CREATE_TABLES:
            await db.execute(stmt)
        await db.commit()


async def upsert_agent(db_path: Path, data: dict[str, str]) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO agents (id, name, description, model_provider, model_name, created_at, updated_at)
            VALUES (:id, :name, :description, :model_provider, :model_name, :created_at, :updated_at)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                model_provider=excluded.model_provider,
                model_name=excluded.model_name,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at
            """,
            data,
        )
        await db.commit()


async def upsert_session(db_path: Path, data: dict[str, str]) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO sessions (id, name, target_type, target_id, status, created_at, updated_at)
            VALUES (:id, :name, :target_type, :target_id, :status, :created_at, :updated_at)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                target_type=excluded.target_type,
                target_id=excluded.target_id,
                status=excluded.status,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at
            """,
            data,
        )
        await db.commit()
