import time

from kieker.task import Task, TaskRunner


class SleepTask(Task):
    def __init__(self, duration: float) -> None:
        super().__init__()
        self.duration = duration

    def run(self) -> None:
        time.sleep(self.duration)


def test_summary_times_parallel() -> None:
    tasks = [SleepTask(0.1) for _ in range(2)]
    runner = TaskRunner(tasks, jobs=2, progress_bar=False)
    runner.run()
    summary = runner.summary["SleepTask"]
    assert summary.user_time - summary.wall_time > 0.05


def test_summary_times_sequential() -> None:
    tasks = [SleepTask(0.1) for _ in range(2)]
    runner = TaskRunner(tasks, jobs=1, progress_bar=False)
    runner.run()
    summary = runner.summary["SleepTask"]
    assert abs(summary.user_time - summary.wall_time) < 0.05


class SetAttrTask(Task):
    def __init__(self, value: int) -> None:
        super().__init__()
        self.value = value
        self.result: int | None = None

    def run(self) -> None:
        self.result = self.value


def test_parallel_results_available() -> None:
    tasks = [SetAttrTask(1), SetAttrTask(2)]
    runner = TaskRunner(tasks, jobs=2, progress_bar=False)
    runner.run()
    assert sorted(t.result for t in runner.tasks) == [1, 2]
