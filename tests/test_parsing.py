"""Tests for parsing code and writing results to an in-memory database."""

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from textwrap import dedent
from typing import Generator

import kieker
from conftest import PrettyRow, SCHEMA_PATH
from kieker.parse import ParseModuleTask
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
    """A context manager running the parse => write pipeline."""
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
