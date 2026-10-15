"""Investigation persistence.

``InvestigationStore`` is the interface; ``SQLiteInvestigationStore`` is the default
zero-dependency implementation. A Postgres/Dynamo implementation only needs the same
five coroutines.
"""
from __future__ import annotations

import asyncio
import sqlite3
import threading
from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas import Investigation, InvestigationStatus, InvestigationSummary, utcnow


class InvestigationStore(ABC):
    @abstractmethod
    async def init(self) -> None: ...

    @abstractmethod
    async def save(self, inv: Investigation) -> None: ...

    @abstractmethod
    async def get(self, inv_id: str) -> Investigation | None: ...

    @abstractmethod
    async def list(self, limit: int, offset: int, q: str | None) -> tuple[list[InvestigationSummary], int]: ...

    @abstractmethod
    async def delete(self, inv_id: str) -> bool: ...


class SQLiteInvestigationStore(InvestigationStore):
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            if str(self._path) != ":memory:":
                self._path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _run(self, fn):
        def locked():
            with self._lock:
                return fn(self._connect())
        return asyncio.to_thread(locked)

    async def init(self) -> None:
        def setup(conn: sqlite3.Connection) -> None:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS investigations (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    query TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    data TEXT NOT NULL
                )"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS ix_inv_created ON investigations(created_at DESC)")
            # Anything still "running" was interrupted by a restart.
            rows = conn.execute(
                "SELECT data FROM investigations WHERE status IN (?, ?)",
                (InvestigationStatus.RUNNING.value, InvestigationStatus.QUEUED.value),
            ).fetchall()
            for (data,) in rows:
                inv = Investigation.model_validate_json(data)
                inv.status = InvestigationStatus.FAILED
                inv.error = "Investigation interrupted by a service restart."
                inv.finished_at = utcnow()
                self._write(conn, inv)
            conn.commit()

        await self._run(setup)

    @staticmethod
    def _write(conn: sqlite3.Connection, inv: Investigation) -> None:
        conn.execute(
            """INSERT INTO investigations (id, created_at, status, title, query, summary, data)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET status=excluded.status, title=excluded.title,
                 summary=excluded.summary, data=excluded.data""",
            (
                inv.id,
                inv.created_at.isoformat(),
                inv.status.value,
                inv.title,
                inv.query,
                inv.summary().model_dump_json(),
                inv.model_dump_json(),
            ),
        )

    async def save(self, inv: Investigation) -> None:
        snapshot = inv.model_copy(deep=True)

        def write(conn: sqlite3.Connection) -> None:
            self._write(conn, snapshot)
            conn.commit()

        await self._run(write)

    async def get(self, inv_id: str) -> Investigation | None:
        row = await self._run(
            lambda conn: conn.execute("SELECT data FROM investigations WHERE id = ?", (inv_id,)).fetchone()
        )
        return Investigation.model_validate_json(row[0]) if row else None

    async def list(self, limit: int, offset: int, q: str | None) -> tuple[list[InvestigationSummary], int]:
        where, params = "", []
        if q:
            where = "WHERE title LIKE ? OR query LIKE ? OR summary LIKE ?"
            like = f"%{q}%"
            params = [like, like, like]

        def read(conn: sqlite3.Connection):
            total = conn.execute(f"SELECT COUNT(*) FROM investigations {where}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT summary FROM investigations {where} "
                "ORDER BY CASE WHEN status IN (?, ?) THEN 0 ELSE 1 END, created_at DESC LIMIT ? OFFSET ?",
                [*params, InvestigationStatus.RUNNING.value, InvestigationStatus.QUEUED.value, limit, offset],
            ).fetchall()
            return total, rows

        total, rows = await self._run(read)
        return [InvestigationSummary.model_validate_json(r[0]) for r in rows], total

    async def delete(self, inv_id: str) -> bool:
        def remove(conn: sqlite3.Connection) -> bool:
            cur = conn.execute("DELETE FROM investigations WHERE id = ?", (inv_id,))
            conn.commit()
            return cur.rowcount > 0

        return await self._run(remove)

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
