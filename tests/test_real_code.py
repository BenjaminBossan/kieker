"""Tests using a real code base, in this case skorch v1.2.0

Many tests in here cover the same queries as the ones used in
examples/usage-example.md.

"""

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


class TestModules:
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
        assert rows[1].module == "callbacks.logging"
        assert rows[1].function_count == 58
        assert rows[2].module == "_version"
        assert rows[2].function_count == 48
        assert rows[3].module == "hf"
        assert rows[3].function_count == 47
        assert rows[4].module == "utils"
        assert rows[4].function_count == 45
        assert rows[5].module == "callbacks.training"
        assert rows[5].function_count == 42
        assert rows[6].module == "llm.classifier"
        assert rows[6].function_count == 38
        assert rows[7].module == "history"
        assert rows[7].function_count == 32
        assert rows[8].module == "probabilistic"
        assert rows[8].function_count == 29
        assert rows[9].module == "callbacks.scoring"
        assert rows[9].function_count == 25


class TestClasses:
    def test_find_classes_that_inherit_from_neuralnet(
        self, conn: sqlite3.Connection
    ) -> None:
        query = """
            SELECT c.qualified_name
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


class TestParameters:
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
            ORDER BY nparams DESC, f.qualified_name
            LIMIT 10;
            """
        rows = conn.execute(query).fetchall()
        assert len(rows) == 10

        assert rows[0].qualified_name == "net.NeuralNet.__init__"
        assert rows[0].nparams == 21
        assert rows[1].qualified_name == "hf.HuggingfaceTokenizer.__init__"
        assert rows[1].nparams == 16
        assert rows[2].qualified_name == "callbacks.training.Checkpoint.__init__"
        assert rows[2].nparams == 15
        assert rows[3].qualified_name == "llm.classifier.FewShotClassifier.__init__"
        assert rows[3].nparams == 13
        assert (
            rows[4].qualified_name == "callbacks.training.TrainEndCheckpoint.__init__"
        )
        assert rows[4].nparams == 12
        assert rows[5].qualified_name == "_doctor.SkorchDoctor.plot_activations"
        assert rows[5].nparams == 11
        assert rows[6].qualified_name == "_doctor.SkorchDoctor.plot_gradients"
        assert rows[6].nparams == 11
        assert rows[7].qualified_name == "callbacks.logging.MlflowLogger.__init__"
        assert rows[7].nparams == 11
        assert rows[8].qualified_name == "hf.HuggingfacePretrainedTokenizer.__init__"
        assert rows[8].nparams == 11
        assert rows[9].qualified_name == "llm.classifier.ZeroShotClassifier.__init__"
        assert rows[9].nparams == 11


class TestDecorators:
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

        target_qnames = sorted(row.target_qname for row in rows)
        expected_qnames = [
            "callbacks.scoring._cache_net_forward_iter",
            "net.NeuralNet._current_init_context",
            "utils.open_file_like",
        ]
        assert target_qnames == expected_qnames


class TestImports:
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
        assert row.imported == "tabulate.tabulate"
        assert row.file.endswith("logging.py")
        assert row.start_line == 13


class TestAttributes:
    def test_normal_attribute_access(self, conn: sqlite3.Connection) -> None:
        query = """
            SELECT f.qualified_name, a.op_kind, f.file, f.start_line
            FROM attributes a
            JOIN classes c ON a.class_id = c.id
            JOIN functions f ON a.function_id = f.id
            WHERE c.qualified_name = 'net.NeuralNet'
              AND a.attribute = 'module_'
              AND a.op_kind IN ('read', 'assign', 'augassign')
            ORDER BY f.file, f.start_line;
            """
        rows = conn.execute(query).fetchall()
        assert len(rows) == 3

        assert rows[0].qualified_name == "net.NeuralNet.initialize_module"
        assert rows[0].op_kind == "assign"
        assert rows[0].file.endswith("net.py")
        assert rows[0].start_line == 618

        assert rows[1].qualified_name == "net.NeuralNet.infer"
        assert rows[1].op_kind == "read"
        assert rows[1].file.endswith("net.py")
        assert rows[1].start_line == 1536

        assert rows[2].qualified_name == "net.NeuralNet.infer"
        assert rows[2].op_kind == "read"
        assert rows[2].file.endswith("net.py")
        assert rows[2].start_line == 1536
