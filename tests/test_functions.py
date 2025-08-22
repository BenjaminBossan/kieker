import os
import sqlite3


class TestFunctions:
    def test_find_to_numpy(self, conn: sqlite3.Connection) -> None:
        query = """
            SELECT *
            FROM functions
            WHERE qualified_name = 'skorch.utils.to_numpy'
            """
        rows = conn.execute(query).fetchall()
        assert len(rows) == 1

        row = rows[0]
        assert row.name == "to_numpy"
        assert row.qualified_name == "skorch.utils.to_numpy"
        assert row.is_method == 0
        assert row.is_staticmethod == 0
        assert row.is_classmethod == 0
        assert row.is_property == 0
        assert row.is_async == 0
        assert row.file.split(os.sep)[-2:] == ["skorch", "utils.py"]
        assert row.start_line == 127
        assert row.start_col == 0
        assert row.end_line == 164
        assert row.end_col == 20
        assert row.property_kind is None
        assert len(row.docstring.split("\n")) == 7
        assert row.def_text.startswith("def to_numpy(X)")
