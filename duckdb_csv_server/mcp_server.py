"""MCP tool definitions for loading CSV files into DuckDB and querying them."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from duckdb_csv_server import db
from duckdb_csv_server.config import get_settings

mcp = FastMCP(
    name="duckdb-csv-mcp-server",
    instructions=(
        "Tools for loading one or more CSV files into an in-process DuckDB "
        "database and querying them with SQL, including joins across files. "
        "If the user hasn't given a CSV file location yet, ask them for it "
        "before calling load_csv. Multiple files can be loaded at once, each "
        "under its own table name, and queried together."
    ),
    stateless_http=True,
    # Mounted under "/mcp" by duckdb_csv_server.main, so the sub-app serves at "/".
    streamable_http_path="/",
)


@mcp.tool()
async def load_csv(
    file_path: str, table_name: str | None = None, replace: bool = False
) -> dict[str, Any]:
    """Load a CSV (or TSV) file into DuckDB as a queryable table.

    If the user hasn't already told you which file to load, ask them for its
    path before calling this tool. The file is scanned lazily (not fully
    loaded into memory), so this works well for large files. Call this
    multiple times to load several files, each with its own table_name, then
    query and join across them with run_query.

    Args:
        file_path: Absolute or relative path to the .csv/.tsv file.
        table_name: Name to register the table under. Defaults to a name
            derived from the file's name. Must be letters/digits/underscores.
        replace: If a table with this name is already loaded, reload it from
            the file instead of raising an error.
    """
    return await db.load_csv(file_path, table_name, replace)


@mcp.tool()
async def list_loaded_tables() -> list[dict[str, Any]]:
    """List the CSV-backed tables currently loaded into DuckDB, with their source file paths."""
    return await db.list_loaded_tables()


@mcp.tool()
async def unload_csv(table_name: str) -> dict[str, Any]:
    """Unload a previously loaded CSV table, freeing it up for reuse under a new file.

    Args:
        table_name: Name of a table previously loaded with load_csv.
    """
    return await db.unload_csv(table_name)


@mcp.tool()
async def get_table_schema(table_name: str) -> dict[str, Any]:
    """Get column names and inferred types for a loaded CSV table.

    Args:
        table_name: Name of a table previously loaded with load_csv.
    """
    return await db.get_table_schema(table_name)


@mcp.tool()
async def preview_table(table_name: str, limit: int = 10) -> dict[str, Any]:
    """Preview the first rows of a loaded CSV table.

    Args:
        table_name: Name of a table previously loaded with load_csv.
        limit: Maximum number of rows to return (default 10).
    """
    return await db.preview_table(table_name, limit)


@mcp.tool()
async def run_query(query: str, max_rows: int = 100) -> dict[str, Any]:
    """Run a read-only SQL SELECT query against the loaded CSV tables.

    Only a single SELECT statement is permitted (CTEs are allowed); joins
    across multiple loaded tables are fine. Any other statement type,
    multiple statements, or file/extension access (COPY, ATTACH, read_csv,
    etc.) is rejected — load files via load_csv instead.

    Args:
        query: The SELECT statement to execute, referencing table names
            returned by load_csv/list_loaded_tables.
        max_rows: Maximum number of rows to return (default 100, capped by
            the server's configured MAX_QUERY_ROWS).
    """
    capped_rows = min(max_rows, get_settings().max_query_rows)
    return await db.run_select_query(query, capped_rows)
