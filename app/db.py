"""Synchronous Azure SQL access, run off the event loop via a threadpool."""

from contextlib import contextmanager
from typing import Any, Iterator

import pyodbc
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.security import validate_select_query


@contextmanager
def _connection() -> Iterator[pyodbc.Connection]:
    settings = get_settings()
    conn = pyodbc.connect(settings.build_connection_string(), timeout=settings.query_timeout_seconds)
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


def _rows_to_dicts(cursor: pyodbc.Cursor, rows: list[Any]) -> list[dict[str, Any]]:
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def _run_query_sync(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    with _connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return _rows_to_dicts(cursor, rows)


async def run_query(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Run a trusted, internally-constructed query (information_schema lookups)."""
    return await run_in_threadpool(_run_query_sync, query, params)


def _run_select_sync(query: str, max_rows: int) -> dict[str, Any]:
    cleaned_query = validate_select_query(query)
    settings = get_settings()
    with _connection() as conn:
        cursor = conn.cursor()
        cursor.timeout = settings.query_timeout_seconds
        cursor.execute(cleaned_query)
        rows = cursor.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        return {
            "rows": _rows_to_dicts(cursor, rows),
            "row_count": len(rows),
            "truncated": truncated,
        }


async def run_select_query(query: str, max_rows: int) -> dict[str, Any]:
    """Validate and run a user-supplied read-only SELECT query."""
    return await run_in_threadpool(_run_select_sync, query, max_rows)
