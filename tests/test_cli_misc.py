import argparse
import logging
import sqlite3
import textwrap
from pathlib import Path

import pytest

from kieker.cli import cmd_create, cmd_map, main
from kieker.log import configure_logger


def _make_create_args(
    paths: list[str],
    output: Path,
    dry_run: bool,
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
        verbose=0,
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

        args_map = argparse.Namespace(db=db)
        cmd_map(args_map)
        out = capsys.readouterr().out.strip().splitlines()
        mod_file = (pkg / "mod.py").as_posix()
        assert out[0] == f"mod  {mod_file}"
        assert f"class C  {mod_file}:1" in out[1]
        assert f"def m {mod_file}:2" in out[2]
        assert f"def f  {mod_file}:6" in out[3]


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


class TestConfigureLogger:
    def test_levels(self) -> None:
        configure_logger(0)
        assert logging.getLogger().level == logging.ERROR
        configure_logger(1)
        assert logging.getLogger().level == logging.INFO
        configure_logger(2)
        assert logging.getLogger().level == logging.DEBUG
