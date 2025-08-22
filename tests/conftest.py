import sqlite3
import subprocess
import textwrap
from pathlib import Path
from typing import Iterator

import pytest

from kieker.cli import create


DBNAME = "db-skorch.sqlite"
HERE = Path(__file__).parent
DBPATH = HERE / DBNAME
REPO_URL = "https://github.com/skorch-dev/skorch.git"
REPO_TAG = "v1.2.0"


def _create_db(path: Path) -> Path:
    # Shallow clone at tag
    try:
        subprocess.check_call(
            ["git", "clone", "--depth", "1", "--branch", REPO_TAG, REPO_URL, str(path)]
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        pytest.skip(f"Could not clone {REPO_URL}@{REPO_TAG}: {exc}")

    create(
        paths=[path / "skorch"],
        roots_str=[str(path)],
        output=DBPATH,
        exclude=[path / "skorch" / "tests"],
    )
    return DBPATH


@pytest.fixture(scope="session")
def work_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-level temp root for relatively expensive ops (like cloning)."""
    return tmp_path_factory.mktemp("kieker_it")


@pytest.fixture(scope="session")
def db_path(work_dir: Path) -> Path:
    if DBPATH.exists():
        return DBPATH

    path = _create_db(work_dir)
    return path


def dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}


class PrettyRow(sqlite3.Row):
    """A row that can be printed nicely."""

    def trim(self, s: str) -> str:
        max_len = 72
        if isinstance(s, str) and len(s) > max_len - 1:
            return textwrap.shorten(s, width=max_len, placeholder="…")
        return s

    def __repr__(self) -> str:
        parts: list[str] = []
        for key in self.keys():
            part = f"{key}={self[key]!r}"
            parts.append(self.trim(part))
        return f"{self.__class__.__name__}(\n  {',\n  '.join(parts)}\n)"

    def __getattr__(self, item: str):
        """Allow attribute access like `row.name`."""
        if item in self.keys():
            return self[item]
        raise AttributeError(f"{self.__class__.__name__} has no attribute {item!r}")


@pytest.fixture
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(db_path)
    try:
        # Strongly recommended for correct FK behavior when you add tests that mutate
        con.execute("PRAGMA foreign_keys = ON;")
        con.row_factory = PrettyRow
        yield con
    finally:
        con.close()
