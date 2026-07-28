"""MCP tool definitions for exploring and querying an Azure SQL database."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from app import db
from app.config import get_settings

mcp = FastMCP(
    name="azure-sql-mcp-server",
    instructions=(
        "Tools for read-only access to an Azure SQL database: list schemas, "
        "list tables, inspect table columns, and run SELECT-only queries."
    ),
    stateless_http=True,
    # Mounted under "/mcp" by app.main, so the sub-app itself serves at "/".
    streamable_http_path="/",
)


@mcp.tool()
async def list_schemas() -> list[str]:
    """List all schemas in the connected Azure SQL database."""
    rows = await db.run_query(
        "SELECT schema_name FROM information_schema.schemata ORDER BY schema_name"
    )
    return [row["schema_name"] for row in rows]


@mcp.tool()
async def list_tables(schema: str | None = None) -> list[dict[str, Any]]:
    """List tables and views in the database.

    Args:
        schema: Optional schema name to filter by (e.g. "dbo"). Lists all schemas if omitted.
    """
    if schema:
        rows = await db.run_query(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = ?
            ORDER BY table_schema, table_name
            """,
            (schema,),
        )
    else:
        rows = await db.run_query(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            ORDER BY table_schema, table_name
            """
        )
    return rows


@mcp.tool()
async def get_table_schema(table: str, schema: str = "dbo") -> dict[str, Any]:
    """Get column definitions and primary key info for a table.

    Args:
        table: Table name.
        schema: Schema the table lives in (defaults to "dbo").
    """
    columns = await db.run_query(
        """
        SELECT column_name, data_type, is_nullable, character_maximum_length,
               numeric_precision, numeric_scale, column_default, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = ? AND table_name = ?
        ORDER BY ordinal_position
        """,
        (schema, table),
    )
    if not columns:
        raise ValueError(f"Table '{schema}.{table}' was not found.")

    primary_key = await db.run_query(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema = ? AND tc.table_name = ?
        ORDER BY kcu.ordinal_position
        """,
        (schema, table),
    )

    return {
        "schema": schema,
        "table": table,
        "columns": columns,
        "primary_key": [row["column_name"] for row in primary_key],
    }


@mcp.tool()
async def run_select_query(query: str, max_rows: int = 100) -> dict[str, Any]:
    """Run a read-only SELECT query against the database.

    Only a single SELECT statement is permitted (CTEs are allowed). Any other
    statement type, multiple statements, or data-modifying keywords are rejected.

    Args:
        query: The SELECT statement to execute.
        max_rows: Maximum number of rows to return (default 100, capped by the
            server's configured MAX_QUERY_ROWS).
    """
    capped_rows = min(max_rows, get_settings().max_query_rows)
    return await db.run_select_query(query, capped_rows)
