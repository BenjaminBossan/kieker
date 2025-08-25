import datetime as dt
import enum
import logging
import multiprocessing
import sys
import time
from dataclasses import dataclass, field
from multiprocessing import cpu_count
from typing import Sequence


logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler(sys.stderr))


class TaskStatus(enum.Enum):
    FAILED = "failed"
    SUCCESS = "success"
    CANCELED = "canceled"


@dataclass
class TaskStat:
    date: dt.datetime
    start: float
    end: float
    status: TaskStatus
    error: Exception | None


@dataclass
class SummaryStat:
    count: int = 0
    success: int = 0
    failed: int = 0
    canceled: int = 0
    user_time: float = 0.0
    _start: float | None = field(default=None, init=False, repr=False)
    _end: float | None = field(default=None, init=False, repr=False)

    @property
    def wall_time(self) -> float:
        if self._start is None or self._end is None:
            return 0.0
        return self._end - self._start


class Task:
    """TODO"""

    def __init__(self) -> None:
        self.has_run = False
        self.stats: list[TaskStat] = []

    def _run(self) -> None:
        error: Exception | None = None
        date = dt.datetime.now(tz=dt.timezone.utc)
        start = time.perf_counter()

        try:
            self.run()
            status = TaskStatus.SUCCESS
        except Exception as exc:
            status = TaskStatus.FAILED
            error = exc
        finally:
            self.has_run = True
            end = time.perf_counter()
            self.stats.append(
                TaskStat(date=date, start=start, end=end, status=status, error=error)
            )

    def run(self) -> None:
        """TODO"""
        raise NotImplementedError("TODO")


def _run_task(task: "Task") -> "Task":
    """Helper to run a task in a separate process."""
    task._run()
    return task


class TaskRunner:
    """Run tasks either sequentially or using multiprocessing."""

    def __init__(
        self,
        tasks: Sequence[Task],
        jobs: int = 1,
        progress_bar: bool = True,
    ) -> None:
        self.tasks = list(tasks)
        self.jobs = jobs if jobs != 0 else cpu_count() or 1
        self.progress_bar = progress_bar
        self.summary: dict[str, SummaryStat] = {}

    def run(self) -> None:
        """Run all tasks."""
        if self.jobs == 1:
            for task in self.tasks:
                task._run()
                if self.progress_bar:
                    # ensure that there is a new line after each task
                    logger.info(f"Completed {task}")
            completed = self.tasks
        else:
            completed = []
            with multiprocessing.Pool(processes=self.jobs) as pool:
                for task in pool.imap_unordered(_run_task, self.tasks):
                    completed.append(task)
                    if self.progress_bar:
                        logger.info(f"Completed {task}")
        self.collect_stats(completed)

    def collect_stats(self, tasks: Sequence[Task]) -> None:
        """Collect stats from all tasks."""
        skipped: list[Task] = []
        summary = self.summary
        for task in tasks:
            if not task.has_run:
                skipped.append(task)
                continue

            key = task.__class__.__name__
            if key not in summary:
                summary[key] = SummaryStat()
            for stat in task.stats:
                summary[key].count += 1
                if stat.status == TaskStatus.SUCCESS:
                    summary[key].success += 1
                elif stat.status == TaskStatus.FAILED:
                    summary[key].failed += 1
                elif stat.status == TaskStatus.CANCELED:
                    summary[key].canceled += 1
                summary[key].user_time += stat.end - stat.start
                if summary[key]._start is None or stat.start < summary[key]._start:
                    summary[key]._start = stat.start
                if summary[key]._end is None or stat.end > summary[key]._end:
                    summary[key]._end = stat.end
