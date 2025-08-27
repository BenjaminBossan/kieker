from pathlib import Path

from kieker.ingest import gather_read_file_tasks


def _make_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# test\n")


def test_exclude_nested_directory(tmp_path: Path) -> None:
    keep = tmp_path / "keep.py"
    _make_file(keep)

    excluded_dir = tmp_path / "pkg"
    _make_file(excluded_dir / "mod.py")
    _make_file(excluded_dir / "nested" / "mod.py")

    tasks = list(gather_read_file_tasks([tmp_path], exclude=[excluded_dir]))
    assert [t.filename for t in tasks] == [keep.resolve()]


def test_exclude_nested_subdirectory(tmp_path: Path) -> None:
    keep1 = tmp_path / "keep.py"
    _make_file(keep1)

    pkg = tmp_path / "pkg"
    _make_file(pkg / "keep2.py")

    nested_exclude = pkg / "nested"
    _make_file(nested_exclude / "skip.py")

    tasks = list(gather_read_file_tasks([tmp_path], exclude=[nested_exclude]))
    filenames = {t.filename for t in tasks}
    assert filenames == {keep1.resolve(), (pkg / "keep2.py").resolve()}
