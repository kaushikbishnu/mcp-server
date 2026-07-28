# mcp-server

An MCP (Model Context Protocol) server, built with FastAPI, that connects to
an Azure SQL database and exposes **read-only** access to it:

- list schemas
- list tables/views
- inspect a table's columns and primary key
- run arbitrary **SELECT-only** queries (everything else is rejected)

The server speaks MCP over HTTP (the "streamable HTTP" transport), so any
MCP-compatible client (Claude Desktop, Claude Code, etc.) can connect to it
at `http://<host>:<port>/mcp`.

## How it works

- `app/mcp_server.py` defines the MCP tools using the official `mcp` Python
  SDK's `FastMCP` helper.
- `app/main.py` is the FastAPI app. It mounts the MCP server's ASGI app at
  `/mcp` and adds a plain `GET /health` endpoint.
- `app/db.py` talks to Azure SQL via `pyodbc`, run off the event loop in a
  threadpool.
- `app/security.py` parses every incoming query with `sqlparse` and rejects
  anything that isn't a single, read-only `SELECT` statement (including
  `SELECT ... INTO`, stacked statements, and stored-procedure calls).
- `app/config.py` reads all configuration from environment variables /
  a `.env` file via `pydantic-settings`.

**Defense in depth:** query validation is the primary guard, but you should
also connect with a SQL login that only has `db_datareader` (read-only)
permissions on the target database, so a bug in the validator can't turn
into a write.

## Prerequisites

- Python 3.11+
- The Microsoft ODBC Driver for SQL Server, plus unixODBC (Linux/macOS), so
  `pyodbc` can connect:
  - **Ubuntu/Debian**: follow Microsoft's instructions to install
    `msodbcsql18` and `unixodbc` (see
    https://learn.microsoft.com/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server).
  - **macOS**: `brew install unixodbc msodbcsql18` (via the `microsoft/mssql-release` tap).
  - **Windows**: install "ODBC Driver 18 for SQL Server" from Microsoft.

## Setup (VS Code)

1. Open this folder in VS Code and install the Python extension if you
   haven't already.
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy the example environment file and fill in your Azure SQL details:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set either `AZURE_SQL_CONNECTION_STRING`, or the
   discrete `AZURE_SQL_SERVER` / `AZURE_SQL_DATABASE` / `AZURE_SQL_USERNAME`
   / `AZURE_SQL_PASSWORD` values. `.env` is already listed in `.gitignore`
   and must never be committed.
5. Run the server:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
   or press **F5** in VS Code — `.vscode/launch.json` is preconfigured to
   run uvicorn with `.env` loaded automatically.

## Verifying it's up

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

MCP clients should point at `http://localhost:8000/mcp` (streamable HTTP
transport). You can sanity-check the protocol directly:

```bash
curl -N -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Tools exposed

| Tool | Description |
| --- | --- |
| `list_schemas()` | List all schemas in the database. |
| `list_tables(schema?)` | List tables/views, optionally filtered by schema. |
| `get_table_schema(table, schema?)` | Columns, types, nullability, and primary key for a table. |
| `run_select_query(query, max_rows?)` | Run a single read-only `SELECT` (CTEs allowed) and return rows as JSON. |

## Configuration reference

All variables are read from the environment / `.env` (see `.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `AZURE_SQL_CONNECTION_STRING` | - | Full ODBC connection string; overrides the discrete fields below. |
| `AZURE_SQL_SERVER` / `AZURE_SQL_DATABASE` / `AZURE_SQL_USERNAME` / `AZURE_SQL_PASSWORD` | - | Used to build a connection string if no full string is given. |
| `AZURE_SQL_DRIVER` | `ODBC Driver 18 for SQL Server` | ODBC driver name. |
| `AZURE_SQL_ENCRYPT` | `true` | Encrypt the connection (recommended for Azure SQL). |
| `AZURE_SQL_TRUST_SERVER_CERTIFICATE` | `false` | Set `true` only for local/dev SQL Server with a self-signed cert. |
| `MAX_QUERY_ROWS` | `1000` | Hard cap on rows returned by `run_select_query`, regardless of the caller's `max_rows`. |
| `QUERY_TIMEOUT_SECONDS` | `30` | Connection/query timeout. |
| `MCP_SERVER_HOST` / `MCP_SERVER_PORT` | `0.0.0.0` / `8000` | Where uvicorn listens. |

## Running tests

```bash
pip install pytest
pytest
```

Tests cover the SELECT-only query validator (`tests/test_security.py`) —
no live database is required.
