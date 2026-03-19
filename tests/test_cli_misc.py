import argparse
import json
import logging
import sqlite3
import textwrap
from pathlib import Path

import pytest

from kieker.cli import cmd_create, cmd_map, main
from kieker.log import configure_logger


def _make_create_args(
    paths: list[str],
    output: Path | None,
    dry_run: bool,
    json: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        paths=paths,
        output=output,
        root=None,
        schema=None,
        exclude=[],
        jobs=1,
        force=False,
        dry_run=dry_run,
        json=json,
        verbose=0,
        no_gitignore=False,
    )


class TestCmdCreate:
    def test_dry_run(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "mod.py").write_text("def foo():\n    return 1\n")
        db = tmp_path / "out.sqlite"
        args = _make_create_args([str(pkg)], db, True)
        with caplog.at_level(logging.INFO):
            cmd_create(args)
        assert "Plan: 1 added, 0 modified, 0 deleted" in caplog.text
        assert not db.exists()

    def test_dry_run_without_output(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        # when using --dry-run, we don't need to indicate an output file
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "mod.py").write_text("def foo():\n    return 1\n")
        args = _make_create_args([str(pkg)], None, True)
        with caplog.at_level(logging.INFO):
            cmd_create(args)
        assert "1 added" in caplog.text

    def test_dry_run_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "mod.py").write_text("def foo():\n    return 1\n")
        db = tmp_path / "out.sqlite"
        args = _make_create_args([str(pkg)], db, True)
        args.json = True
        cmd_create(args)
        payload = json.loads(capsys.readouterr().out)
        mod_file = (pkg / "mod.py").as_posix()
        assert payload["summary"] == {"added": 1, "modified": 0, "deleted": 0}
        assert payload["added"] == [mod_file]
        assert payload["modified"] == []
        assert payload["deleted"] == []

    def test_no_output_without_dry_run_exits(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        # when *not* using --dry-run, we *do* need to indicate an output file
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "mod.py").write_text("def foo():\n    return 1\n")
        args = _make_create_args([str(pkg)], None, False)
        with pytest.raises(SystemExit) as exc_info:
            with caplog.at_level(logging.ERROR):
                cmd_create(args)
        assert exc_info.value.code == 2

    def test_executes(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "mod.py").write_text("def foo():\n    return 1\n")
        db = tmp_path / "out.sqlite"
        args = _make_create_args([str(pkg)], db, False)
        cmd_create(args)
        con = sqlite3.connect(db)
        try:
            row = con.execute(
                """
                SELECT qualified_name
                FROM functions
                WHERE name = 'foo'
                """
            ).fetchone()
            assert row[0] == "mod.foo"
        finally:
            con.close()


class TestCmdMap:
    def test_outputs(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "mod.py").write_text(
            textwrap.dedent(
                """\
                class C:
                    def m(self):
                        pass


                def f():
                    pass
                """
            )
        )
        db = tmp_path / "db.sqlite"
        args = _make_create_args([str(pkg)], db, False)
        cmd_create(args)

        args_map = argparse.Namespace(db=db, json=False)
        cmd_map(args_map)
        out = capsys.readouterr().out.strip().splitlines()
        mod_file = (pkg / "mod.py").as_posix()
        assert out[0] == f"mod  {mod_file}"
        assert f"class C  {mod_file}:1" in out[1]
        assert f"def m {mod_file}:2" in out[2]
        assert f"def f  {mod_file}:6" in out[3]

    def test_outputs_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "mod.py").write_text(
            textwrap.dedent(
                """\
                class C:
                    def m(self):
                        pass


                def f():
                    pass
                """
            )
        )
        db = tmp_path / "db.sqlite"
        args = _make_create_args([str(pkg)], db, False)
        cmd_create(args)

        args_map = argparse.Namespace(db=db, json=True)
        cmd_map(args_map)
        payload = json.loads(capsys.readouterr().out)
        mod_file = (pkg / "mod.py").as_posix()
        assert payload == {
            "modules": [
                {
                    "name": "mod",
                    "file": mod_file,
                    "classes": [
                        {
                            "name": "C",
                            "file": mod_file,
                            "line": 1,
                            "col": 0,
                            "methods": [
                                {
                                    "name": "m",
                                    "file": mod_file,
                                    "line": 2,
                                    "col": 4,
                                }
                            ],
                        }
                    ],
                    "functions": [
                        {
                            "name": "f",
                            "file": mod_file,
                            "line": 6,
                            "col": 0,
                        }
                    ],
                }
            ]
        }


class TestMain:
    def test_create_dry_run_sets_info(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "mod.py").write_text("def foo():\n    return 1\n")
        db = tmp_path / "out.sqlite"
        main(["create", str(pkg), "-o", str(db), "--dry-run"])
        assert logging.getLogger().level == logging.INFO
        assert not db.exists()

    def test_examples_branch(self, capsys: pytest.CaptureFixture[str]) -> None:
        main(["examples", "--list"])
        out = capsys.readouterr().out.strip()
        assert out.startswith("0.")

    def test_examples_json_branch(self, capsys: pytest.CaptureFixture[str]) -> None:
        main(["examples", "--list", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["examples"][0]["id"] == "0"


class TestConfigureLogger:
    def test_levels(self) -> None:
        configure_logger(0)
        assert logging.getLogger().level == logging.ERROR
        configure_logger(1)
        assert logging.getLogger().level == logging.INFO
        configure_logger(2)
        assert logging.getLogger().level == logging.DEBUG
