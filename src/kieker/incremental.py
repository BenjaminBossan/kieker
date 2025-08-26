from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


CURRENT_PARSER_VERSION = 1
CURRENT_SCHEMA_VERSION = 1


@dataclass
class FileInfo:
    """Metadata about a scanned Python file."""

    path: str
    size_bytes: int
    mtime_ns: int
    sha256: str


@dataclass
class Plan:
    """Set of changes to apply to the database."""

    added: list[FileInfo]
    modified: list[FileInfo]
    deleted: list[str]

    def is_empty(self) -> bool:
        """Return True if the plan contains no work."""
        return not (self.added or self.modified or self.deleted)


def _stat_file(path: Path) -> tuple[int, int]:
    st = path.stat()
    size = st.st_size
    mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
    return size, mtime_ns


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_paths(paths: Sequence[Path], *, exclude: Sequence[Path] = (), root: Path) -> list[FileInfo]:
    """Walk the given paths and collect FileInfo records."""
    results: list[FileInfo] = []
    exclude = [p.resolve() for p in exclude]
    for p in paths:
        p = p.resolve()
        if any(str(p).startswith(str(ex)) for ex in exclude):
            continue
        if p.is_symlink():
            continue
        if p.is_file() and p.suffix == ".py":
            size, mtime = _stat_file(p)
            sha = _hash_file(p)
            rel = p.relative_to(root).as_posix()
            results.append(FileInfo(rel, size, mtime, sha))
        elif p.is_dir():
            for child in p.iterdir():
                results.extend(scan_paths([child], exclude=exclude, root=root))
    return results


def _load_db_modules(conn: sqlite3.Connection) -> dict[str, tuple[str, int, int]]:
    cur = conn.execute(
        "SELECT file, file_hash, parser_version, schema_version FROM modules"
    )
    return {row[0]: (row[1], int(row[2]), int(row[3])) for row in cur.fetchall()}


def plan_changes(
    conn: sqlite3.Connection | None,
    files: Iterable[FileInfo],
    *,
    force: bool = False,
) -> Plan:
    """Compare scanned files with the database and determine necessary changes."""
    files_by_path = {f.path: f for f in files}
    if conn is None or force:
        return Plan(list(files_by_path.values()), [], [])

    db_modules = _load_db_modules(conn)
    added: list[FileInfo] = []
    modified: list[FileInfo] = []
    for path, info in files_by_path.items():
        db_row = db_modules.get(path)
        if db_row is None:
            added.append(info)
        else:
            file_hash, parser_version, schema_version = db_row
            if (
                file_hash != info.sha256
                or parser_version != CURRENT_PARSER_VERSION
                or schema_version != CURRENT_SCHEMA_VERSION
            ):
                modified.append(info)
    deleted = [p for p in db_modules.keys() if p not in files_by_path]
    return Plan(added, modified, deleted)

