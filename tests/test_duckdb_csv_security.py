from pathlib import Path

import pytest

from duckdb_csv_server.security import (
    IdentifierValidationError,
    PathValidationError,
    QueryValidationError,
    default_table_name,
    validate_csv_path,
    validate_identifier,
    validate_select_query,
)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM orders",
        "select id, name from customers where id = 1",
        "SELECT * FROM orders;",
        "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent",
        "SELECT o.id, c.name FROM orders o JOIN customers c ON o.customer_id = c.id",
    ],
)
def test_valid_select_queries_pass(query):
    validate_select_query(query)


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "DROP TABLE orders",
        "INSERT INTO orders (id) VALUES (1)",
        "UPDATE orders SET name = 'x'",
        "DELETE FROM orders",
        "SELECT * FROM orders; DROP TABLE orders",
        "SELECT * FROM orders; SELECT * FROM customers",
        "ATTACH 'secrets.db' AS s",
        "COPY orders TO 'out.csv'",
        "SELECT * FROM read_csv_auto('/etc/passwd')",
        "PRAGMA database_list",
        "INSTALL httpfs",
        "CALL some_proc()",
        "EXPORT DATABASE 'dir'",
    ],
)
def test_invalid_queries_are_rejected(query):
    with pytest.raises(QueryValidationError):
        validate_select_query(query)


@pytest.mark.parametrize("name", ["orders", "orders_2024", "_temp", "Orders"])
def test_valid_identifiers_pass(name):
    validate_identifier(name)


@pytest.mark.parametrize("name", ["", "1orders", "orders; DROP", "orders-2024", "orders table"])
def test_invalid_identifiers_are_rejected(name):
    with pytest.raises(IdentifierValidationError):
        validate_identifier(name)


def test_default_table_name_sanitizes_and_lowercases():
    assert default_table_name(Path("My Sales-2024.csv")) == "my_sales_2024"
    assert default_table_name(Path("1data.csv")) == "t_1data"


def test_validate_csv_path_rejects_missing_file(tmp_path):
    with pytest.raises(PathValidationError):
        validate_csv_path(str(tmp_path / "missing.csv"), [tmp_path])


def test_validate_csv_path_rejects_non_csv_extension(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("a,b\n1,2\n")
    with pytest.raises(PathValidationError):
        validate_csv_path(str(f), [tmp_path])


def test_validate_csv_path_rejects_outside_allowed_dirs(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    f = outside / "data.csv"
    f.write_text("a,b\n1,2\n")
    with pytest.raises(PathValidationError):
        validate_csv_path(str(f), [allowed])


def test_validate_csv_path_accepts_file_inside_allowed_dir(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("a,b\n1,2\n")
    resolved = validate_csv_path(str(f), [tmp_path])
    assert resolved == f.resolve()


def test_validate_csv_path_allows_any_dir_when_unrestricted(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("a,b\n1,2\n")
    resolved = validate_csv_path(str(f), [])
    assert resolved == f.resolve()
