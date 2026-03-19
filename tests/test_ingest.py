from pathlib import Path

import pytest

from kieker.read import gather_read_file_tasks


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


# .gitignore tests
#
# Shared fixture: a semi-realistic project layout with source code, build
# artifacts, a virtualenv, generated files, and a .gitignore that excludes
# some of them.
#
#   project/
#   ├── .gitignore          # build/\n venv/\n auto_generated_*.py\n **/__pycache__/\n
#   ├── setup.py
#   ├── src/
#   │   ├── app.py
#   │   └── utils/
#   │       └── helpers.py
#   ├── tests/
#   │   └── test_app.py
#   ├── build/
#   │   └── lib/
#   │       └── compiled.py
#   ├── venv/
#   │   └── lib/
#   │       └── site.py
#   ├── auto_generated_schema.py
#   └── src/utils/__pycache__/
#       └── helpers.cpython.py


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a semi-realistic Python project with a .gitignore."""
    root = tmp_path / "project"

    # Source files (should be kept)
    _make_file(root / "setup.py")
    _make_file(root / "src" / "app.py")
    _make_file(root / "src" / "utils" / "helpers.py")
    _make_file(root / "tests" / "test_app.py")

    # Build artifacts (gitignored via directory pattern)
    _make_file(root / "build" / "lib" / "compiled.py")

    # Virtualenv (gitignored via directory pattern)
    _make_file(root / "venv" / "lib" / "site.py")

    # Generated file (gitignored via glob pattern)
    _make_file(root / "auto_generated_schema.py")

    # Pycache (gitignored via nested glob pattern)
    _make_file(root / "src" / "utils" / "__pycache__" / "helpers.cpython.py")

    (root / ".gitignore").write_text(
        "build/\nvenv/\nauto_generated_*.py\n**/__pycache__/\n"
    )
    return root


KEPT_FILES = {
    "setup.py",
    "src/app.py",
    "src/utils/helpers.py",
    "tests/test_app.py",
}

IGNORED_FILES = {
    "build/lib/compiled.py",
    "venv/lib/site.py",
    "auto_generated_schema.py",
    "src/utils/__pycache__/helpers.cpython.py",
}


def _filenames(tasks):
    return {t.filename for t in tasks}


def _rel_filenames(tasks, root: Path) -> set[str]:
    return {str(t.filename.relative_to(root.resolve())) for t in tasks}


def test_gitignore_respected_by_default(project: Path) -> None:
    """Directory, glob, and nested glob patterns in .gitignore are all respected."""
    tasks = list(gather_read_file_tasks([project], exclude=[]))
    rel = _rel_filenames(tasks, project)
    assert rel == KEPT_FILES


def test_no_gitignore_flag_disables_filtering(project: Path) -> None:
    """respect_gitignore=False includes all files; True excludes some."""
    tasks_with = list(gather_read_file_tasks([project], exclude=[]))
    tasks_without = list(
        gather_read_file_tasks([project], exclude=[], respect_gitignore=False)
    )
    rel_with = _rel_filenames(tasks_with, project)
    rel_without = _rel_filenames(tasks_without, project)

    # Sanity: with gitignore enabled, ignored files are absent
    assert rel_with == KEPT_FILES

    # With gitignore disabled, everything is included
    assert rel_without == KEPT_FILES | IGNORED_FILES


def test_no_gitignore_file_includes_everything(tmp_path: Path) -> None:
    """When there is no .gitignore, all files are included regardless."""
    _make_file(tmp_path / "a.py")
    _make_file(tmp_path / "sub" / "b.py")

    tasks = list(gather_read_file_tasks([tmp_path], exclude=[]))
    assert _filenames(tasks) == {
        (tmp_path / "a.py").resolve(),
        (tmp_path / "sub" / "b.py").resolve(),
    }
