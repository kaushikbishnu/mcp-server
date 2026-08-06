"""FastAPI app exposing the DuckDB CSV MCP server over streamable HTTP."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from duckdb_csv_server.mcp_server import mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="DuckDB CSV MCP Server",
    description="MCP server for loading CSV files into DuckDB and querying them with SQL.",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# The MCP protocol (tools/list, tools/call, etc.) is served here over
# streamable HTTP, e.g. POST http://localhost:8001/mcp
app.mount("/mcp", mcp.streamable_http_app())
