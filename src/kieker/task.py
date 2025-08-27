import datetime as dt
import enum
import logging
import multiprocessing
import sys
import time
from dataclasses import dataclass, field
from multiprocessing import cpu_count
from typing import Any, Generic, Sequence, TypeVar, cast


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


TResult = TypeVar("TResult")

class ResultTask(Generic[TResult]):
    """Idempotent task that returns a result on demand."""

    def __init__(self) -> None:
        self.has_run = False
        self._result: TResult | Exception | None = None
        self.stats: list[TaskStat] = []

    def run(self) -> TResult:
        raise NotImplementedError

    def get_result(self) -> TResult:
        if self.has_run:
            if isinstance(self._result, Exception):
                raise self._result
            return cast(TResult, self._result)

        date = dt.datetime.now(tz=dt.timezone.utc)
        start = time.perf_counter()
        error: Exception | None = None
        try:
            result = self.run()
            status = TaskStatus.SUCCESS
            self._result = result
        except Exception as exc:
            error = exc
            status = TaskStatus.FAILED
            self._result = exc
        end = time.perf_counter()
        self.has_run = True
        self.stats.append(
            TaskStat(date=date, start=start, end=end, status=status, error=error)
        )
        if error is not None:
            raise error
        return cast(TResult, self._result)


TTask = TypeVar("TTask", bound="ResultTask[Any]")


def _run_task(task: TTask) -> TTask:
    """Helper to run a task in a separate process."""
    task.get_result()
    return task


class TaskRunner(Generic[TTask]):
    """Run tasks either sequentially or using multiprocessing."""

    def __init__(
        self,
        tasks: Sequence[TTask],
        jobs: int = 1,
        progress_bar: bool = True,
    ) -> None:
        self.tasks: list[TTask] = list(tasks)
        self.jobs = jobs if jobs != 0 else cpu_count() or 1
        self.progress_bar = progress_bar
        self.summary: dict[str, SummaryStat] = {}

    def run(self) -> list[TTask]:
        """Run all tasks and return the completed ones."""
        completed: list[TTask]
        if self.jobs == 1:
            for task in self.tasks:
                task.get_result()
                if self.progress_bar:
                    # ensure that there is a new line after each task
                    logger.info(f"Completed {task}")
            completed = list(self.tasks)
        else:
            completed = []
            with multiprocessing.Pool(processes=self.jobs) as pool:
                for task in pool.imap_unordered(_run_task, self.tasks):
                    completed.append(task)
                    if self.progress_bar:
                        logger.info(f"Completed {task}")
        self.tasks = completed
        self.collect_stats(completed)
        return self.tasks

    def collect_stats(self, tasks: Sequence[ResultTask[Any]]) -> None:
        """Collect stats from all tasks."""
        skipped: list[ResultTask[Any]] = []
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
                start = summary[key]._start
                if start is None:
                    summary[key]._start = stat.start
                elif stat.start < start:
                    summary[key]._start = stat.start

                end = summary[key]._end
                if end is None:
                    summary[key]._end = stat.end
                elif stat.end > end:
                    summary[key]._end = stat.end
