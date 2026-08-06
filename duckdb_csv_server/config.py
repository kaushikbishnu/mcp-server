"""Application configuration, loaded from environment variables / a .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Prefixed so this server's env vars never collide with the Azure SQL
    # server's (app/config.py) when both are configured in the same .env.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="DUCKDB_"
    )

    # Where DuckDB stores its catalog. Defaults to an in-memory database, so
    # loaded tables disappear when the server restarts. Set to a file path
    # (e.g. "./duckdb_csv.db") to persist loaded tables across restarts.
    database_path: str | None = None

    # Comma-separated list of directories that CSV files may be loaded from.
    # Any path outside these directories (after resolving "..", symlinks,
    # etc.) is rejected. Defaults to the current working directory only —
    # widen this deliberately if CSVs live elsewhere.
    csv_allowed_dirs: str = "."

    # Query safety / behavior
    max_query_rows: int = 1000

    # HTTP server
    server_host: str = "0.0.0.0"
    server_port: int = 8001

    def resolved_allowed_dirs(self) -> list[Path]:
        dirs = [d.strip() for d in self.csv_allowed_dirs.split(",") if d.strip()]
        return [Path(d).expanduser().resolve() for d in dirs]


@lru_cache
def get_settings() -> Settings:
    return Settings()
