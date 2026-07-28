import pytest

from app.security import QueryValidationError, validate_select_query


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM dbo.Customers",
        "select id, name from dbo.Customers where id = 1",
        "SELECT * FROM dbo.Customers;",
        "WITH recent AS (SELECT * FROM dbo.Orders) SELECT * FROM recent",
        "SELECT TOP 10 * FROM dbo.Customers ORDER BY id",
    ],
)
def test_valid_select_queries_pass(query):
    validate_select_query(query)


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "DROP TABLE dbo.Customers",
        "INSERT INTO dbo.Customers (id) VALUES (1)",
        "UPDATE dbo.Customers SET name = 'x'",
        "DELETE FROM dbo.Customers",
        "SELECT * FROM dbo.Customers; DROP TABLE dbo.Customers",
        "SELECT * INTO NewTable FROM dbo.Customers",
        "EXEC sp_who",
        "SELECT * FROM dbo.Customers; SELECT * FROM dbo.Orders",
        "ALTER TABLE dbo.Customers ADD COLUMN x INT",
        "TRUNCATE TABLE dbo.Customers",
        "GRANT SELECT ON dbo.Customers TO public",
        "EXEC xp_cmdshell 'dir'",
    ],
)
def test_invalid_queries_are_rejected(query):
    with pytest.raises(QueryValidationError):
        validate_select_query(query)
