import datetime as dt
import enum
import logging
import sys
import time
from dataclasses import dataclass
from typing import Literal, Sequence


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
    total_time: float = 0.0


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


class TaskRunner:
    """TODO"""

    def __init__(
        self,
        tasks: Sequence[Task],
        run_type: Literal["sequential"] = "sequential",
        progress_bar: bool = True,
    ) -> None:
        self.tasks = tasks
        self.run_type = run_type
        self.progress_bar = progress_bar
        self.summary: dict[str, SummaryStat] = {}

    def run(self) -> None:
        """TODO"""
        if self.run_type == "sequential":
            for task in self.tasks:
                task._run()
                if self.progress_bar:
                    # ensure that there is a new line after each task
                    logger.info(f"Completed {task}")
        else:
            raise ValueError(
                f"{self.__class__.__name__} got unknown argument for run_type: {self.run_type}. Valid arguments: 'sequential'."
            )
        self.collect_stats(self.tasks)

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
                summary[key].total_time += stat.end - stat.start
