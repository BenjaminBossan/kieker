import argparse
import json
import logging
import sqlite3
from pathlib import Path

import pytest

from kieker.cli import EXAMPLES, cmd_examples, create


def make_args(
    id: str | None = None, list_: bool = False, json_: bool = False
) -> argparse.Namespace:
    return argparse.Namespace(id=id, list=list_, json=json_)


def test_examples_lists_all(capsys):
    cmd_examples(make_args())
    captured = capsys.readouterr()
    lines = captured.out.strip().splitlines()
    # don't test specifics, just that we get multiple lines
    assert len(lines) >= 5


def test_examples_shows_single_example(capsys):
    ex = EXAMPLES[1]
    cmd_examples(make_args(id=ex["id"]))
    captured = capsys.readouterr()
    assert f"-- Example {ex['id']}: {ex['title']}" in captured.out
    assert ex["sql"] in captured.out


def test_examples_list_json(capsys):
    cmd_examples(make_args(list_=True, json_=True))
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert len(payload["examples"]) == len(EXAMPLES)
    assert payload["examples"][0] == {
        "id": EXAMPLES[0]["id"],
        "title": EXAMPLES[0]["title"],
        "sql": EXAMPLES[0]["sql"],
    }


def test_examples_single_json(capsys):
    ex = EXAMPLES[1]
    cmd_examples(make_args(id=ex["id"], json_=True))
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["example"] == {
        "id": ex["id"],
        "title": ex["title"],
        "sql": ex["sql"],
    }


def test_examples_unknown_id(caplog):
    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as excinfo:
            cmd_examples(make_args(id="99"))
    assert excinfo.value.code == 2
    assert "Unknown example id: 99" in caplog.text


def test_create_uses_path_as_root(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "mod.py").write_text(
        """\
def foo():
    pass
"""
    )

    db = tmp_path / "out.sqlite"
    create(paths=[pkg], output=db)

    con = sqlite3.connect(db)
    try:
        row = con.execute(
            "SELECT qualified_name FROM functions WHERE name = 'foo'"
        ).fetchone()
        assert row[0] == "mod.foo"
    finally:
        con.close()


def test_create_parallel_jobs(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "mod.py").write_text(
        """\
def foo():
    pass
"""
    )

    db = tmp_path / "out.sqlite"
    create(paths=[pkg], output=db, jobs=2)

    con = sqlite3.connect(db)
    try:
        row = con.execute(
            "SELECT qualified_name FROM functions WHERE name = 'foo'",
        ).fetchone()
        assert row[0] == "mod.foo"
    finally:
        con.close()
