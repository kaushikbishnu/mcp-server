"""Validation for CSV file paths, table identifiers, and read-only queries."""

import re
from pathlib import Path

import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import DDL, DML, Keyword

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Statement-level keywords that must never appear, even inside an otherwise
# well-formed SELECT. Covers both standard SQL data-modifying statements and
# DuckDB-specific commands that can read/write arbitrary files on disk
# (ATTACH, COPY, EXPORT/IMPORT, INSTALL/LOAD, PRAGMA, SET) or bypass the
# load_csv allow-list entirely (the read_csv/read_parquet/read_json/glob
# table functions).
_FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT", "REPLACE",
    "DROP", "ALTER", "CREATE", "TRUNCATE", "RENAME",
    "GRANT", "REVOKE", "DENY",
    "EXEC", "EXECUTE", "CALL",
    "ATTACH", "DETACH", "COPY", "EXPORT", "IMPORT",
    "INSTALL", "LOAD", "PRAGMA", "SET", "RESET",
    "VACUUM", "CHECKPOINT",
    "INTO",
}

# Function/keyword substrings blocked regardless of how sqlparse tokenizes
# them (DuckDB-specific syntax like ATTACH isn't in sqlparse's keyword list,
# so it may not come through as a Keyword token at all).
_FORBIDDEN_PATTERN = re.compile(
    r"\b("
    r"attach|detach|copy|export|import|install|load|pragma|"
    r"read_csv\w*|read_parquet\w*|read_json\w*|read_text\w*|read_blob\w*|"
    r"glob|sqlite_scan|postgres_scan"
    r")\b",
    re.IGNORECASE,
)


class QueryValidationError(ValueError):
    pass


class PathValidationError(ValueError):
    pass


class IdentifierValidationError(ValueError):
    pass


def _statement_type(statement: Statement) -> str:
    """Like sqlparse's get_type(), but understands statements starting with WITH (CTEs)."""
    first_token = statement.token_first(skip_cm=True)
    if first_token is None:
        return "UNKNOWN"
    value = first_token.value.upper()
    if first_token.ttype in DML:
        return value
    if value == "WITH":
        return "SELECT"
    return "UNKNOWN"


def validate_select_query(raw_query: str) -> str:
    """Raise QueryValidationError unless raw_query is a single, read-only SELECT statement.

    Returns the trimmed query on success.
    """
    if not raw_query or not raw_query.strip():
        raise QueryValidationError("Query must not be empty.")

    if _FORBIDDEN_PATTERN.search(raw_query):
        match = _FORBIDDEN_PATTERN.search(raw_query)
        raise QueryValidationError(f"'{match.group(0)}' is not allowed in read-only queries.")

    statements = [s for s in sqlparse.parse(raw_query) if s.token_first(skip_cm=True) is not None]
    if len(statements) == 0:
        raise QueryValidationError("Query must not be empty.")
    if len(statements) > 1:
        raise QueryValidationError("Only a single statement is allowed per query.")

    statement = statements[0]

    if _statement_type(statement) != "SELECT":
        raise QueryValidationError("Only SELECT statements are allowed.")

    for token in statement.flatten():
        upper_value = token.value.upper()
        if token.ttype in (DDL,) or (token.ttype is Keyword and upper_value in _FORBIDDEN_KEYWORDS):
            raise QueryValidationError(f"'{token.value}' is not allowed in read-only queries.")
        if token.ttype in DML and upper_value != "SELECT":
            raise QueryValidationError(f"'{token.value}' is not allowed in read-only queries.")

    cleaned = str(statement).strip()
    cleaned = cleaned[:-1].strip() if cleaned.endswith(";") else cleaned
    return cleaned


def validate_identifier(name: str) -> str:
    """Raise IdentifierValidationError unless name is a safe SQL identifier."""
    if not name or not _IDENTIFIER_PATTERN.match(name):
        raise IdentifierValidationError(
            f"'{name}' is not a valid table name. Use letters, digits, and underscores, "
            "and don't start with a digit."
        )
    return name


def default_table_name(file_path: Path) -> str:
    """Derive a safe default table name from a CSV file's name."""
    stem = re.sub(r"[^A-Za-z0-9_]", "_", file_path.stem)
    if not stem or stem[0].isdigit():
        stem = f"t_{stem}"
    return stem.lower()


def validate_csv_path(raw_path: str, allowed_dirs: list[Path]) -> Path:
    """Resolve raw_path and ensure it's a real CSV file inside an allowed directory."""
    if not raw_path or not raw_path.strip():
        raise PathValidationError("File path must not be empty.")

    path = Path(raw_path).expanduser().resolve()

    if not path.exists():
        raise PathValidationError(f"File not found: {path}")
    if not path.is_file():
        raise PathValidationError(f"Not a file: {path}")
    if path.suffix.lower() not in (".csv", ".tsv"):
        raise PathValidationError(f"Only .csv/.tsv files are allowed, got: {path.suffix}")

    if allowed_dirs and not any(
        path == base or base in path.parents for base in allowed_dirs
    ):
        raise PathValidationError(
            f"'{path}' is outside the allowed CSV directories: "
            f"{', '.join(str(d) for d in allowed_dirs)}"
        )

    return path
