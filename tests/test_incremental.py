import sqlite3
from pathlib import Path

import kieker.incremental as incremental
from kieker.cli import create, plan


def test_incremental_flow(tmp_path: Path, monkeypatch):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    f = pkg / "mod.py"
    f.write_text("a = 1\n")
    db = tmp_path / "out.sqlite"

    # Cold start
    p, _, _ = plan(paths=[pkg], output=db)
    assert sorted(fi.path for fi in p.added) == ["mod.py"]
    assert not p.modified and not p.deleted
    create(paths=[pkg], output=db)
    con = sqlite3.connect(db)
    try:
        (count,) = con.execute("SELECT COUNT(*) FROM modules").fetchone()
        assert count == 1
    finally:
        con.close()

    # No-op
    p, _, _ = plan(paths=[pkg], output=db)
    assert p.is_empty()
    create(paths=[pkg], output=db)
    con = sqlite3.connect(db)
    try:
        (count,) = con.execute("SELECT COUNT(*) FROM modules").fetchone()
        assert count == 1
    finally:
        con.close()

    # Single edit
    con = sqlite3.connect(db)
    try:
        (old_hash,) = con.execute(
            "SELECT file_hash FROM modules WHERE file='mod.py'"
        ).fetchone()
    finally:
        con.close()
    f.write_text("a = 2\n")
    p, _, _ = plan(paths=[pkg], output=db)
    assert [fi.path for fi in p.modified] == ["mod.py"]
    create(paths=[pkg], output=db)
    con = sqlite3.connect(db)
    try:
        (new_hash,) = con.execute(
            "SELECT file_hash FROM modules WHERE file='mod.py'"
        ).fetchone()
        assert new_hash != old_hash
    finally:
        con.close()

    # Delete
    f.unlink()
    p, _, _ = plan(paths=[pkg], output=db)
    assert p.deleted == ["mod.py"]
    create(paths=[pkg], output=db)
    con = sqlite3.connect(db)
    try:
        (count,) = con.execute("SELECT COUNT(*) FROM modules").fetchone()
        assert count == 0
    finally:
        con.close()

    # Version bump
    f.write_text("a = 3\n")
    create(paths=[pkg], output=db)
    monkeypatch.setattr(
        incremental,
        "CURRENT_PARSER_VERSION",
        incremental.CURRENT_PARSER_VERSION + 1,
    )
    p, _, _ = plan(paths=[pkg], output=db)
    assert [fi.path for fi in p.modified] == ["mod.py"]
    create(paths=[pkg], output=db)
    con = sqlite3.connect(db)
    try:
        (parser_version,) = con.execute(
            "SELECT parser_version FROM modules WHERE file='mod.py'"
        ).fetchone()
        assert parser_version == incremental.CURRENT_PARSER_VERSION
    finally:
        con.close()
