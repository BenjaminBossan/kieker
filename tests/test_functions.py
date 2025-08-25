import os
import sqlite3


class TestFunctions:
    def test_find_to_numpy(self, conn: sqlite3.Connection) -> None:
        query = """
            SELECT *
            FROM functions
            WHERE qualified_name = 'utils.to_numpy'
            """
        rows = conn.execute(query).fetchall()
        assert len(rows) == 1

        row = rows[0]
        assert row.name == "to_numpy"
        assert row.qualified_name == "utils.to_numpy"
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
        assert row.def_text.strip().startswith("def to_numpy(X)")

    def test_find_calls_to_asarray(self, conn: sqlite3.Connection) -> None:
        query = """
            SELECT f.file, f.start_line, f.end_line, f.qualified_name
            FROM calls c
            JOIN functions f ON f.id = c.caller_id
            WHERE c.callee_repr = 'np.asarray'
            ORDER BY f.file, f.start_line;
            """
        rows = conn.execute(query).fetchall()
        assert len(rows) == 7

        modules = sorted(row.file.rsplit(os.sep)[-1] for row in rows)
        expected = [
            "classifier.py",
            "helper.py",
            "helper.py",
            "hf.py",
            "hf.py",
            "hf.py",
            "utils.py",
        ]
        assert modules == expected

    def test_find_long_functions_without_docstring(
        self, conn: sqlite3.Connection
    ) -> None:
        query = """
            SELECT f.qualified_name, fm.lines_of_code
            FROM functions f
            JOIN function_metrics fm ON fm.function_id = f.id
            WHERE fm.lines_of_code > 50
              AND (f.docstring IS NULL OR f.docstring = '')
            ORDER BY fm.lines_of_code DESC;
            """
        rows = conn.execute(query).fetchall()
        assert len(rows) == 3

        assert rows[0].qualified_name == "history.History.__getitem__"
        assert rows[0].lines_of_code == 60
        assert rows[1].qualified_name == "net.NeuralNet.__init__"
        assert rows[1].lines_of_code == 52
        assert rows[2].qualified_name == "_version._cmpkey"
        assert rows[2].lines_of_code == 51

    def test_find_modules_with_many_functions(self, conn: sqlite3.Connection) -> None:
        query = """
            SELECT m.module, COUNT(f.id) AS function_count
            FROM modules m
            JOIN functions f ON f.module_id = m.id
            GROUP BY m.module
            ORDER BY function_count DESC
            LIMIT 10;
            """
        rows = conn.execute(query).fetchall()
        assert len(rows) == 10

        assert rows[0].module == "net"
        assert rows[0].function_count == 92

    def test_find_classes_that_inherit_from_neuralnet(
        self, conn: sqlite3.Connection
    ) -> None:
        query = """
            SELECT c.name AS subclass_name,
              c.file,
              c.start_line,
              c.end_line,
              c.qualified_name
            FROM classes c
            JOIN inheritance i ON i.subclass_id = c.id
            WHERE i.superclass_name = 'NeuralNet'
            ORDER BY c.file, c.start_line;
            """
        rows = conn.execute(query).fetchall()
        assert len(rows) == 4

        qualified_names = {row.qualified_name for row in rows}
        expected = {
            "classifier.NeuralNetClassifier",
            "classifier.NeuralNetBinaryClassifier",
            "probabilistic.GPBase",
            "regressor.NeuralNetRegressor",
        }
        assert qualified_names == expected

    def test_find_functions_with_highest_parameter_count(
        self, conn: sqlite3.Connection
    ) -> None:
        query = """
            WITH param_counts AS (
              SELECT p.function_id, COUNT(*) AS nparams
              FROM parameters p
              GROUP BY p.function_id
            )
            SELECT f.qualified_name, nparams
            FROM param_counts pc
            JOIN functions f ON f.id = pc.function_id
            WHERE pc.nparams >= 8
            ORDER BY nparams DESC, f.qualified_name;
            """
        rows = conn.execute(query).fetchall()
        assert len(rows) == 22

        assert rows[0].qualified_name == "net.NeuralNet.__init__"
        assert rows[0].nparams == 21

    def test_find_classes_and_functions_with_contextmanager_decorator(
        self, conn: sqlite3.Connection
    ) -> None:
        query = """
            SELECT (CASE d.target_kind WHEN 'class' THEN 'class' ELSE 'function' END) AS kind,
                   (CASE d.target_kind
                      WHEN 'class'    THEN (SELECT qualified_name FROM classes  WHERE id = d.target_id)
                      ELSE                 (SELECT qualified_name FROM functions WHERE id = d.target_id)
                    END) AS target_qname, d.file
            FROM decorators d
            WHERE d.name_repr = 'contextmanager'
            ORDER BY kind, target_qname;
        """
        rows = conn.execute(query).fetchall()
        assert len(rows) == 3

        assert [row.kind for row in rows] == ["function"] * 3
        modules = sorted(row.file.rsplit(os.sep)[-1] for row in rows)
        expected = ["net.py", "scoring.py", "utils.py"]
        assert modules == expected

    def test_find_modules_that_import_tabulate(self, conn: sqlite3.Connection) -> None:
        query = """
            SELECT m.module, i.imported, i.file, i.start_line
            FROM imports i
            JOIN modules m ON m.id = i.module_id
            WHERE i.imported LIKE 'tabulate.%'
            ORDER BY m.module, i.file, i.start_line;
        """
        rows = conn.execute(query).fetchall()
        assert len(rows) == 1

        row = rows[0]
        assert row.module == "callbacks.logging"
        assert row.file.endswith("logging.py")
