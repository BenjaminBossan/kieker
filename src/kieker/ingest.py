import hashlib
from pathlib import Path
from typing import Iterator, Sequence

from .task import Task


class ReadFileTask(Task):
    """A task that reads a file."""

    def __init__(self, filename: str | Path):
        super().__init__()
        self.filename = Path(filename).resolve()
        self.content: str | None = None
        self.hash: str | None = None
        self.size_bytes: int | None = None
        self.mtime_ns: int | None = None

    def run(self) -> None:
        with open(self.filename) as f:
            content = f.read()
        stat = self.filename.stat()
        self.content = content
        self.hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.size_bytes = stat.st_size
        self.mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(filename={str(self.filename)})"


def _is_valid_file(filename: str | Path) -> bool:
    return Path(filename).suffix == ".py"


def gather_read_file_tasks(
    paths: Sequence[Path], exclude: Sequence[Path]
) -> Iterator[ReadFileTask]:
    """Expand the given paths into a list of `ReadFileTask`s (recursively)."""
    exclude = list(exclude)
    for path in paths:
        path = path.resolve()
        if any(str(path).startswith(str(ex)) for ex in exclude):
            continue

        # file
        if path.is_file() and _is_valid_file(path):
            if path.is_symlink():
                continue
            yield ReadFileTask(path)
            continue

        # directory
        if path.is_dir():
            for child in path.iterdir():
                yield from gather_read_file_tasks([child], exclude=exclude)
