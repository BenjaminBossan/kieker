# mypy: ignore-errors
import argparse
import logging

import pytest

from kieker.cli import EXAMPLES, cmd_examples


def make_args(id: str | None = None, list_: bool = False) -> argparse.Namespace:
    return argparse.Namespace(id=id, list=list_)


def test_examples_lists_all(capsys):
    cmd_examples(make_args())
    captured = capsys.readouterr()
    expected_lines = [f"{ex['id']}. {ex['title']}" for ex in EXAMPLES]
    assert captured.out.strip().splitlines() == expected_lines


def test_examples_shows_single_example(capsys):
    ex = EXAMPLES[1]
    cmd_examples(make_args(id=ex["id"]))
    captured = capsys.readouterr()
    assert f"-- Example {ex['id']}: {ex['title']}" in captured.out
    assert ex["sql"] in captured.out


def test_examples_unknown_id(caplog):
    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as excinfo:
            cmd_examples(make_args(id="99"))
    assert excinfo.value.code == 2
    assert "Unknown example id: 99" in caplog.text
