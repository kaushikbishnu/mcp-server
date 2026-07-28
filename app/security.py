"""Validation that only ever lets read-only SELECT statements through."""

import re

import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import DDL, DML, Keyword

# Statement-level keywords that must never appear, even inside an otherwise
# well-formed SELECT (e.g. "SELECT ... INTO new_table", "SELECT ... FOR UPDATE").
_FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT",
    "DROP", "ALTER", "CREATE", "TRUNCATE", "RENAME",
    "GRANT", "REVOKE", "DENY",
    "EXEC", "EXECUTE", "CALL",
    "INTO",
    "sp_executesql",
}

# Blocked regardless of statement type — extended stored procs, xp_cmdshell, etc.
_FORBIDDEN_PATTERN = re.compile(r"\b(xp_|sp_)\w+", re.IGNORECASE)


class QueryValidationError(ValueError):
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
        if _FORBIDDEN_PATTERN.search(token.value):
            raise QueryValidationError(f"'{token.value}' is not allowed in read-only queries.")

    cleaned = str(statement).strip()
    # Strip a single trailing semicolon, if present.
    cleaned = cleaned[:-1].strip() if cleaned.endswith(";") else cleaned
    return cleaned
