import sqlite3
from pathlib import Path

import kieker
from kieker.cli import create, create_plan


def test_incremental_flow(tmp_path: Path) -> None:
    repo = tmp_path / "pkg"
    repo.mkdir()
    f1 = repo / "a.py"
    f1.write_text("def a():\n    return 1\n")
    f2 = repo / "b.py"
    f2.write_text("def b():\n    return 2\n")
    db = tmp_path / "out.sqlite"

    # Cold start
    plan = create_plan(paths=[repo], output=db, jobs=2)
    assert sorted(plan.added) == [str(f1), str(f2)]
    assert not plan.modified and not plan.deleted
    create(paths=[repo], output=db, plan=plan, jobs=2)
    con = sqlite3.connect(db)
    try:
        (count,) = con.execute("SELECT COUNT(*) FROM modules").fetchone()
        assert count == 2
    finally:
        con.close()

    # No-op
    plan = create_plan(paths=[repo], output=db, jobs=2)
    assert plan.added == [] and plan.modified == [] and plan.deleted == []

    # Single edit
    f1.write_text("def a():\n    return 42\n")
    plan = create_plan(paths=[repo], output=db, jobs=2)
    assert plan.modified == [str(f1)]
    create(paths=[repo], output=db, plan=plan, jobs=2)
    con = sqlite3.connect(db)
    try:
        (count,) = con.execute("SELECT COUNT(*) FROM modules").fetchone()
        assert count == 2
    finally:
        con.close()

    # Delete
    f1.unlink()
    plan = create_plan(paths=[repo], output=db, jobs=2)
    assert plan.deleted == [str(f1)]
    create(paths=[repo], output=db, plan=plan, jobs=2)
    con = sqlite3.connect(db)
    try:
        (count,) = con.execute("SELECT COUNT(*) FROM modules").fetchone()
        assert count == 1
    finally:
        con.close()

    # version bump
    old = kieker.__version__
    kieker.__version__ = "9.9.9"
    try:
        plan = create_plan(paths=[repo], output=db, jobs=2)
        assert plan.modified == [str(f2)]
    finally:
        kieker.__version__ = old
