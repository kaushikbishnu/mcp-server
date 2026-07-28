"""FastAPI app exposing the Azure SQL MCP server over streamable HTTP."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.mcp_server import mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Azure SQL MCP Server",
    description="MCP server for read-only exploration and querying of an Azure SQL database.",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# The MCP protocol (tools/list, tools/call, etc.) is served here over
# streamable HTTP, e.g. POST http://localhost:8000/mcp
app.mount("/mcp", mcp.streamable_http_app())
