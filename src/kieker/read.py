import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from pathspec import PathSpec

from .task import ResultTask


@dataclass
class ReadFileResult:
    content: str
    hash: str
    size_bytes: int
    mtime_ns: int


class ReadFileTask(ResultTask[ReadFileResult]):
    """A task that reads a file."""

    def __init__(self, filename: str | Path):
        super().__init__()
        self.filename = Path(filename).resolve()

    def run(self) -> ReadFileResult:
        with open(self.filename) as f:
            content = f.read()
        stat = self.filename.stat()
        return ReadFileResult(
            content=content,
            hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            size_bytes=stat.st_size,
            mtime_ns=getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9)),
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(filename={str(self.filename)})"


def _is_valid_file(filename: str | Path) -> bool:
    return Path(filename).suffix == ".py"


def _load_gitignore_spec(root: Path) -> PathSpec | None:
    """Load .gitignore patterns from a directory, returning None if absent."""
    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return None
    lines = gitignore.read_text(encoding="utf-8").splitlines()
    return PathSpec.from_lines("gitwildmatch", lines)


def gather_read_file_tasks(
    paths: Sequence[Path],
    exclude: Sequence[Path],
    respect_gitignore: bool = True,
) -> Iterator[ReadFileTask]:
    """Expand the given paths into a list of `ReadFileTask`s (recursively)."""
    exclude_paths = {Path(ex).resolve() for ex in exclude}
    for path in map(Path, paths):
        path = path.resolve()
        if any(path.is_relative_to(ex) for ex in exclude_paths):
            continue

        # file
        if path.is_file() and _is_valid_file(path):
            if path.is_symlink():
                continue
            yield ReadFileTask(path)
            continue

        # directory
        if path.is_dir():
            gitignore_spec = _load_gitignore_spec(path) if respect_gitignore else None
            for file in path.rglob("*.py"):
                file = file.resolve()
                if any(file.is_relative_to(ex) for ex in exclude_paths):
                    continue
                if file.is_symlink():
                    continue
                if gitignore_spec is not None:
                    rel = str(file.relative_to(path))
                    if gitignore_spec.match_file(rel):
                        continue
                if _is_valid_file(file):
                    yield ReadFileTask(file)
