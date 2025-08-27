# AGENTS Instructions

## Development instructions
- Run `make checks` to format, lint, and type-check Python code.
- Document public APIs and keep functions type annotated.
- Prefer simple, functional code, isolate the non-functional part (e.g. to the CLI).
- Even with YAGNI, prefer code that is easy to change and extend in the future.

## Test instructions
- Run `pytest tests` to execute the test suite.
- Check if the newly added code is covered by inspecting the code coverage report.

## PR instructions
- Summarize changes and list tests run in PR descriptions.
- If the solution is non-trivial, the PR description should elaborate on why it was chosen and not something else.
