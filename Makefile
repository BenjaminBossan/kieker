.PHONY: checks

CHECK_PATHS=src tests

checks:
	ruff format $(CHECK_PATHS)
	ruff check $(CHECK_PATHS)
	mypy --strict src
