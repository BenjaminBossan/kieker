"""Tests for parsing code and writing results to an in-memory database."""

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from textwrap import dedent
from typing import Generator

import kieker
from conftest import PrettyRow, SCHEMA_PATH
from kieker.parse import ParseModuleTask, infer_module_name
from kieker.read import ReadFileResult
from kieker.task import ResultTask
from kieker.write import WriteToDbTask, ensure_schema


class StringReadFileTask(ResultTask[ReadFileResult]):
    """A dummy `ReadFileTask` that returns pre-defined source code."""

    def __init__(self, content: str, filename: str = "mod.py") -> None:
        super().__init__()
        self.content = dedent(content)
        self.filename = Path(filename).resolve()

    def run(self) -> ReadFileResult:
        content = self.content
        return ReadFileResult(
            content=content,
            hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            size_bytes=len(content.encode("utf-8")),
            mtime_ns=0,
        )


@contextmanager
def pipeline(
    code: str, filename: str = "mod.py"
) -> Generator[sqlite3.Connection, None, None]:
    """Run the parse => write pipeline and yield a DB connection."""
    read_task = StringReadFileTask(code, filename)
    parse_task = ParseModuleTask(read_task, roots=[Path(".")])
    conn = sqlite3.connect(":memory:")
    conn.row_factory = PrettyRow
    ensure_schema(conn, SCHEMA_PATH)
    WriteToDbTask(parse_task, conn, kieker.__version__).get_result()
    try:
        yield conn
    finally:
        conn.close()


def test_function_written() -> None:
    """Functions are parsed and persisted to the database."""

    code = """
    def foo(x: int) -> int:
        return x + 1
    """
    with pipeline(code) as conn:
        rows = conn.execute(
            "SELECT name, qualified_name, is_async FROM functions"
        ).fetchall()
        assert len(rows) == 1

        row = rows[0]
        assert row.name == "foo"
        assert row.qualified_name == "mod.foo"
        assert row.is_async == 0


def test_imports_and_calls() -> None:
    """Imports and calls are detected and stored."""

    code = """
    import os
    from math import sin as s
    from sys import *

    def foo():
        os.path.join("a", "b")
        s(1)
    """
    with pipeline(code) as conn:
        imports = conn.execute(
            "SELECT imported, alias, is_from_import FROM imports ORDER BY imported"
        ).fetchall()
        assert {row.imported for row in imports} == {"os", "math.sin", "sys.*"}
        assert next(r for r in imports if r.imported == "math.sin").alias == "s"

        calls = conn.execute(
            """
            SELECT f.qualified_name AS caller_qname, c.callee_repr
            FROM calls c JOIN functions f ON c.caller_id = f.id
            ORDER BY c.callee_repr
            """
        ).fetchall()
        assert any(
            row.caller_qname == "mod.foo" and row.callee_repr == "os.path.join"
            for row in calls
        )
        assert any(
            row.caller_qname == "mod.foo" and row.callee_repr == "s" for row in calls
        )


def test_class_decorators_and_inheritance() -> None:
    """Classes, decorators, and inheritance relationships are parsed."""

    code = """
    import dataclasses, typing

    @dataclasses.dataclass(order=True)
    class Base:
        x: int

    class Child(Base, typing.List[int]):
        @staticmethod
        def static() -> None:
            pass

        @classmethod
        def klass(cls) -> None:
            pass

        @property
        def prop(self) -> int:
            return 1

        @prop.setter
        def prop(self, value: int) -> int:
            return value

        @prop.deleter
        def prop(self) -> None:
            pass
    """
    with pipeline(code) as conn:
        decorator_names = {
            row.name_repr for row in conn.execute("SELECT name_repr FROM decorators")
        }
        assert {
            "dataclasses.dataclass",
            "staticmethod",
            "classmethod",
            "property",
            "prop.setter",
            "prop.deleter",
        }.issubset(decorator_names)

        inh_rows = conn.execute(
            """
            SELECT c.qualified_name AS subclass_qname, i.superclass_name
            FROM inheritance i JOIN classes c ON i.subclass_id = c.id
            """
        ).fetchall()
        inh = {(row.subclass_qname, row.superclass_name) for row in inh_rows}
        assert ("mod.Child", "Base") in inh
        assert ("mod.Child", "typing.List") in inh

        fn_rows = conn.execute(
            "SELECT qualified_name, is_staticmethod, is_classmethod, is_property, property_kind FROM functions"
        ).fetchall()
        fns = {row.qualified_name: row for row in fn_rows}
        assert fns["mod.Child.static"].is_staticmethod
        assert fns["mod.Child.klass"].is_classmethod
        assert fns["mod.Child.prop"].is_property
        assert fns["mod.Child.prop#setter"].property_kind == "setter"
        assert fns["mod.Child.prop#deleter"].property_kind == "deleter"


def test_parameter_parsing() -> None:
    """Different parameter kinds are recognized."""

    code = """
    def complex(a, /, b: int = 1, *args: str, c, d=..., **kwargs: float):
        pass

    def star_only(*, kw):
        pass
    """
    with pipeline(code) as conn:
        params = conn.execute(
            """
            SELECT f.qualified_name AS function_qname, p.name, p.pos_kind, p.default_kind,
                   p.default_repr, p.annotation_repr
            FROM parameters p JOIN functions f ON p.function_id = f.id
            WHERE f.qualified_name = 'mod.complex'
            """
        ).fetchall()
        by_name = {row.name: row for row in params}
        assert by_name["a"].pos_kind == "posonly"
        assert by_name["b"].annotation_repr == "int"
        assert by_name["b"].default_kind == "expr"
        assert by_name["args"].pos_kind == "var_pos"
        assert by_name["args"].annotation_repr == "str"
        assert by_name["c"].pos_kind == "kwonly"
        assert by_name["d"].default_kind == "expr"
        assert by_name["d"].default_repr == "..."
        assert by_name["kwargs"].pos_kind == "var_kw"
        assert by_name["kwargs"].annotation_repr == "float"

        star_params = conn.execute(
            """
            SELECT p.name, p.pos_kind
            FROM parameters p JOIN functions f ON p.function_id = f.id
            WHERE f.qualified_name = 'mod.star_only'
            """
        ).fetchall()
        star_names = {row.name for row in star_params}
        assert star_names == {"*", "kw"}
        star_var = next(r for r in star_params if r.name == "*")
        assert star_var.pos_kind == "var_pos"
        kw_param = next(r for r in star_params if r.name == "kw")
        assert kw_param.pos_kind == "kwonly"


def test_control_flow_metrics_and_calls() -> None:
    """Cyclomatic complexity and calls are collected."""

    code = """
    def complicated(a):
        if a and True:
            for i in range(3):
                pass
        while False:
            pass
        try:
            pass
        except ValueError:
            pass
        with open("x"):
            pass
        match a:
            case 1:
                pass
    """
    with pipeline(code) as conn:
        metrics = conn.execute(
            """
            SELECT f.qualified_name AS function_qname, m.cyclomatic, m.lines_of_code
            FROM function_metrics m JOIN functions f ON m.function_id = f.id
            """
        ).fetchone()
        assert metrics.function_qname == "mod.complicated"
        assert metrics.cyclomatic == 8
        assert metrics.lines_of_code == 15

        callees = {
            row.callee_repr
            for row in conn.execute(
                """
                SELECT c.callee_repr
                FROM calls c JOIN functions f ON c.caller_id = f.id
                WHERE f.qualified_name = 'mod.complicated'
                """
            )
        }
        assert {"range", "open"}.issubset(callees)


def test_infer_module_name(tmp_path: Path) -> None:
    """`infer_module_name` chooses the most specific root and falls back."""

    file = tmp_path / "pkg" / "sub" / "mod.py"
    roots = [tmp_path, tmp_path / "pkg"]
    assert infer_module_name(file, roots) == "sub.mod"

    file2 = tmp_path / "outer.py"
    fallback = infer_module_name(file2, [tmp_path / "other"])
    p = file2.with_suffix("")
    expected = ".".join([part for part in p.parts if part not in (".", "")])
    assert fallback == expected
