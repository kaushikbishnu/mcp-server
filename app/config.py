"""Application configuration, loaded from environment variables / a .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Provide either a full ODBC connection string ...
    azure_sql_connection_string: str | None = None

    # ... or the discrete parts, which are assembled into one at startup.
    azure_sql_server: str | None = None
    azure_sql_database: str | None = None
    azure_sql_username: str | None = None
    azure_sql_password: str | None = None
    azure_sql_driver: str = "ODBC Driver 18 for SQL Server"
    azure_sql_encrypt: bool = True
    azure_sql_trust_server_certificate: bool = False

    # Query safety / behavior
    max_query_rows: int = 1000
    query_timeout_seconds: int = 30

    # HTTP server
    mcp_server_host: str = "0.0.0.0"
    mcp_server_port: int = 8000

    def build_connection_string(self) -> str:
        if self.azure_sql_connection_string:
            return self.azure_sql_connection_string

        missing = [
            name
            for name, value in (
                ("AZURE_SQL_SERVER", self.azure_sql_server),
                ("AZURE_SQL_DATABASE", self.azure_sql_database),
                ("AZURE_SQL_USERNAME", self.azure_sql_username),
                ("AZURE_SQL_PASSWORD", self.azure_sql_password),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "Missing Azure SQL connection settings. Provide AZURE_SQL_CONNECTION_STRING, "
                f"or all of: {', '.join(missing)}."
            )

        encrypt = "yes" if self.azure_sql_encrypt else "no"
        trust_cert = "yes" if self.azure_sql_trust_server_certificate else "no"
        return (
            f"DRIVER={{{self.azure_sql_driver}}};"
            f"SERVER={self.azure_sql_server};"
            f"DATABASE={self.azure_sql_database};"
            f"UID={self.azure_sql_username};"
            f"PWD={self.azure_sql_password};"
            f"Encrypt={encrypt};"
            f"TrustServerCertificate={trust_cert};"
            "Connection Timeout=30;"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
