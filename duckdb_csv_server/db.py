"""Synchronous DuckDB access, run off the event loop via a threadpool.

A single DuckDB connection is shared for the life of the process. CSV files
loaded via `load_csv` become views registered in that connection's catalog,
so they can be queried (and joined with each other) by name until the
process restarts or they're explicitly unloaded.
"""

import threading
from typing import Any

import duckdb
from starlette.concurrency import run_in_threadpool

from duckdb_csv_server.config import get_settings
from duckdb_csv_server.security import (
    default_table_name,
    validate_csv_path,
    validate_identifier,
    validate_select_query,
)

_lock = threading.Lock()
_connection: duckdb.DuckDBPyConnection | None = None
_loaded_tables: dict[str, dict[str, Any]] = {}


def _get_connection() -> duckdb.DuckDBPyConnection:
    global _connection
    if _connection is None:
        settings = get_settings()
        _connection = duckdb.connect(database=settings.database_path or ":memory:")
    return _connection


def _describe(conn: duckdb.DuckDBPyConnection, table_name: str) -> list[dict[str, Any]]:
    rows = conn.execute(f'DESCRIBE "{table_name}"').fetchall()
    columns = [d[0] for d in conn.description]
    return [dict(zip(columns, row)) for row in rows]


def _load_csv_sync(file_path: str, table_name: str | None, replace: bool) -> dict[str, Any]:
    settings = get_settings()
    path = validate_csv_path(file_path, settings.resolved_allowed_dirs())
    resolved_name = validate_identifier(table_name) if table_name else default_table_name(path)

    with _lock:
        conn = _get_connection()
        if resolved_name in _loaded_tables and not replace:
            raise ValueError(
                f"Table '{resolved_name}' is already loaded. Pass replace=true to reload it, "
                "or choose a different table_name."
            )

        # DuckDB can't prepare/bind parameters inside DDL (CREATE VIEW), so the
        # path is embedded as a quoted SQL string literal. It's safe to inline
        # here because validate_csv_path() has already resolved it to a real
        # file that exists inside an allowed directory; the escaping below is
        # just to handle literal quote characters in the path correctly.
        escaped_path = str(path).replace("'", "''")
        create_stmt = (
            f'CREATE OR REPLACE VIEW "{resolved_name}" AS '
            f"SELECT * FROM read_csv_auto('{escaped_path}', union_by_name=true)"
        )
        conn.execute(create_stmt)
        columns = _describe(conn, resolved_name)
        _loaded_tables[resolved_name] = {"file_path": str(path), "columns": columns}

        return {
            "table_name": resolved_name,
            "file_path": str(path),
            "columns": columns,
        }


async def load_csv(file_path: str, table_name: str | None, replace: bool) -> dict[str, Any]:
    return await run_in_threadpool(_load_csv_sync, file_path, table_name, replace)


def _list_loaded_tables_sync() -> list[dict[str, Any]]:
    with _lock:
        return [
            {"table_name": name, "file_path": info["file_path"], "column_count": len(info["columns"])}
            for name, info in sorted(_loaded_tables.items())
        ]


async def list_loaded_tables() -> list[dict[str, Any]]:
    return await run_in_threadpool(_list_loaded_tables_sync)


def _unload_csv_sync(table_name: str) -> dict[str, Any]:
    validate_identifier(table_name)
    with _lock:
        if table_name not in _loaded_tables:
            raise ValueError(f"Table '{table_name}' is not currently loaded.")
        conn = _get_connection()
        conn.execute(f'DROP VIEW IF EXISTS "{table_name}"')
        del _loaded_tables[table_name]
        return {"table_name": table_name, "unloaded": True}


async def unload_csv(table_name: str) -> dict[str, Any]:
    return await run_in_threadpool(_unload_csv_sync, table_name)


def _get_table_schema_sync(table_name: str) -> dict[str, Any]:
    validate_identifier(table_name)
    with _lock:
        if table_name not in _loaded_tables:
            raise ValueError(f"Table '{table_name}' is not currently loaded.")
        info = _loaded_tables[table_name]
        return {"table_name": table_name, "file_path": info["file_path"], "columns": info["columns"]}


async def get_table_schema(table_name: str) -> dict[str, Any]:
    return await run_in_threadpool(_get_table_schema_sync, table_name)


def _preview_table_sync(table_name: str, limit: int) -> dict[str, Any]:
    validate_identifier(table_name)
    with _lock:
        if table_name not in _loaded_tables:
            raise ValueError(f"Table '{table_name}' is not currently loaded.")
        conn = _get_connection()
        rows = conn.execute(f'SELECT * FROM "{table_name}" LIMIT ?', [limit]).fetchall()
        columns = [d[0] for d in conn.description]
        return {"rows": [dict(zip(columns, row)) for row in rows], "row_count": len(rows)}


async def preview_table(table_name: str, limit: int) -> dict[str, Any]:
    return await run_in_threadpool(_preview_table_sync, table_name, limit)


def _run_select_sync(query: str, max_rows: int) -> dict[str, Any]:
    cleaned_query = validate_select_query(query)
    with _lock:
        conn = _get_connection()
        cursor = conn.execute(cleaned_query)
        rows = cursor.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        columns = [d[0] for d in cursor.description]
        return {
            "rows": [dict(zip(columns, row)) for row in rows],
            "row_count": len(rows),
            "truncated": truncated,
        }


async def run_select_query(query: str, max_rows: int) -> dict[str, Any]:
    return await run_in_threadpool(_run_select_sync, query, max_rows)
