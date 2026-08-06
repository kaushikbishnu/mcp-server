# mcp-server

Two independent MCP (Model Context Protocol) servers, built with FastAPI,
each exposing **read-only** access to a data source over MCP's "streamable
HTTP" transport, so any MCP-compatible client (Claude Desktop, Claude Code,
etc.) can connect to them:

- **`app/`** — connects to an Azure SQL database. See below.
- **`duckdb_csv_server/`** — loads CSV/TSV files into an in-process DuckDB
  database and lets you query (and join) them with SQL. See
  [DuckDB CSV MCP Server](#duckdb-csv-mcp-server) below.

Both servers can run at the same time (on different ports) since they're
independent FastAPI apps.

## Azure SQL MCP Server

Exposes:

- list schemas
- list tables/views
- inspect a table's columns and primary key
- run arbitrary **SELECT-only** queries (everything else is rejected)

It's available at `http://<host>:<port>/mcp`.

### How it works

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

### Prerequisites

- Python 3.11+
- The Microsoft ODBC Driver for SQL Server, plus unixODBC (Linux/macOS), so
  `pyodbc` can connect:
  - **Ubuntu/Debian**: follow Microsoft's instructions to install
    `msodbcsql18` and `unixodbc` (see
    https://learn.microsoft.com/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server).
  - **macOS**: `brew install unixodbc msodbcsql18` (via the `microsoft/mssql-release` tap).
  - **Windows**: install "ODBC Driver 18 for SQL Server" from Microsoft.

### Setup (VS Code)

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
   or press **F5** in VS Code and pick "Azure SQL MCP Server (uvicorn,
   reload)" — `.vscode/launch.json` is preconfigured to run uvicorn with
   `.env` loaded automatically.

### Verifying it's up

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

### Tools exposed

| Tool | Description |
| --- | --- |
| `list_schemas()` | List all schemas in the database. |
| `list_tables(schema?)` | List tables/views, optionally filtered by schema. |
| `get_table_schema(table, schema?)` | Columns, types, nullability, and primary key for a table. |
| `run_select_query(query, max_rows?)` | Run a single read-only `SELECT` (CTEs allowed) and return rows as JSON. |

### Configuration reference

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

## DuckDB CSV MCP Server

Loads one or more CSV/TSV files into an in-process [DuckDB](https://duckdb.org/)
database and exposes **read-only** SQL access over them — including joins
across files loaded in the same session. It's available at
`http://<host>:<port>/mcp` (default port `8001`, so it can run alongside the
Azure SQL server on `8000`).

There's no database to configure up front: in the chat window, tell the
assistant which CSV file to load (or it will ask you for the path), and it
calls `load_csv` for you. Load as many files as you need, then ask questions
that get translated into `run_query` calls — including joins across the
files you've loaded.

### How it works

- `duckdb_csv_server/mcp_server.py` defines the MCP tools.
- `duckdb_csv_server/main.py` is the FastAPI app, mounting the MCP server at
  `/mcp` plus a `GET /health` endpoint.
- `duckdb_csv_server/db.py` holds a single DuckDB connection for the life of
  the process. `load_csv` registers a file as a `CREATE OR REPLACE VIEW ...
  read_csv_auto(...)`, so large files are scanned lazily from disk rather
  than fully materialized in memory. A lock serializes access to the shared
  connection across concurrent tool calls.
- `duckdb_csv_server/security.py` validates every `load_csv` path and every
  `run_query` statement:
  - **Path validation**: the file must exist, have a `.csv`/`.tsv`
    extension, and resolve inside one of the configured `CSV_ALLOWED_DIRS`
    (symlinks and `..` are resolved before the check) — this is what stops
    the tool from being used to read arbitrary files off disk.
  - **Query validation**: only a single, read-only `SELECT` (CTEs allowed)
    is accepted, via the same `sqlparse`-based approach as the Azure SQL
    server, plus an extra keyword/function blocklist for DuckDB-specific
    commands that can touch the filesystem or catalog outside `load_csv`
    (`ATTACH`, `COPY`, `PRAGMA`, `INSTALL`/`LOAD`, `read_csv`/`read_parquet`/
    `read_json`, etc.).
- `duckdb_csv_server/config.py` reads configuration from environment
  variables / `.env`, all prefixed `DUCKDB_` so it can share a `.env` file
  with the Azure SQL server without clashing.

### Setup (VS Code)

1. Install dependencies (shared with the Azure SQL server):
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` if you haven't already, and adjust the
   `DUCKDB_*` variables — in particular `DUCKDB_CSV_ALLOWED_DIRS`, which
   defaults to `.` (the current directory). Set it to a comma-separated list
   of directories your CSV files actually live in.
3. Run the server:
   ```bash
   uvicorn duckdb_csv_server.main:app --reload --host 0.0.0.0 --port 8001
   ```
   or press **F5** in VS Code and pick "DuckDB CSV MCP Server (uvicorn,
   reload)".

### Verifying it's up

```bash
curl http://localhost:8001/health
# {"status":"ok"}
```

### Tools exposed

| Tool | Description |
| --- | --- |
| `load_csv(file_path, table_name?, replace?)` | Load a CSV/TSV file as a queryable table. Table name defaults to a sanitized version of the filename. |
| `list_loaded_tables()` | List currently loaded tables and their source file paths. |
| `unload_csv(table_name)` | Drop a loaded table so its name can be reused. |
| `get_table_schema(table_name)` | Column names and inferred types for a loaded table. |
| `preview_table(table_name, limit?)` | First N rows of a loaded table (default 10). |
| `run_query(query, max_rows?)` | Run a single read-only `SELECT` (joins across loaded tables allowed) and return rows as JSON. |

### Configuration reference

All variables are read from the environment / `.env` (see `.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `DUCKDB_DATABASE_PATH` | - (in-memory) | Set to a file path to persist loaded tables across restarts. |
| `DUCKDB_CSV_ALLOWED_DIRS` | `.` | Comma-separated directories `load_csv` is allowed to read from. |
| `DUCKDB_MAX_QUERY_ROWS` | `1000` | Hard cap on rows returned by `run_query`, regardless of the caller's `max_rows`. |
| `DUCKDB_SERVER_HOST` / `DUCKDB_SERVER_PORT` | `0.0.0.0` / `8001` | Where uvicorn listens. |

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

Tests cover the SELECT-only query validators and path/identifier validation
for both servers (`tests/test_security.py`,
`tests/test_duckdb_csv_security.py`) — no live database or CSV files are
required.
