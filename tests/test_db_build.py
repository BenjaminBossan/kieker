import sqlite3


def test_schema_tables_exist(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        ORDER BY name
        """
    ).fetchall()
    names = {r[0] for r in rows}
    expected = {
        "modules", "classes", "functions", "parameters",
        "decorators", "imports", "inheritance", "calls",
        "function_metrics",
    }
    missing = expected - names
    assert not missing


def test_modules_have_rows(conn: sqlite3.Connection) -> None:
    # Only a smoke test for now; tighten later for the chosen repo.
    n, = conn.execute("SELECT COUNT(*) FROM modules").fetchone()
    assert n >= 1


def test_functions_have_rows(conn: sqlite3.Connection) -> None:
    n, = conn.execute("SELECT COUNT(*) FROM functions").fetchone()
    assert n >= 1
