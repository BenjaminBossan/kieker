# AGENTS Instructions

## Querying the code
VERY IMPORTANT: Use kieker itself to query the code:

```
kieker create src/kieker -o code.sqlite
# check modules
sqlite3 -header -column code.sqlite "SELECT module, file from modules;"
# project map of classes and functions
kieker map code.sqlite
# list a few examples
kieker examples --list
```

Only use `sed`, `cat`, `tail`, `grep` etc. if kieker does not work for the purpose.

Two examples:

If you search for the code of the function called `ResultTask`, instead of

```
$ rg "class ResultTask" src/kieker/*.py
src/kieker/task.py
48:class ResultTask(Generic[TResult]):
$ sed -n '48,80p' src/kieker/task.py
```

do:

```
$ sqlite3 code.sqlite "SELECT def_text
FROM classes
WHERE qualified_name like '%ResultTask';"
```

To find each instance in the code where the `configure_logger` function is being called, run:

```
$ sqlite3 -header -column code.sqlite \
"SELECT f.file, c.start_line call_line, f.start_line fn_start, f.end_line fn_end, f.qualified_name fn_name
FROM calls c
JOIN functions f ON f.id = c.caller_id
WHERE c.callee_repr = 'configure_logger'
ORDER BY f.file, f.start_line;"
```

Use the returned information to make targeted queries and changes to the code. If you need more examples, run `kieker examples --list` and follow from there.

## Development instructions
- The source files and `schema.sql` are located in `src/kieker/`.
- The tests are located in `tests/`.
- Before committing, run `make checks` to format, lint, and type-check the code.
- Document public APIs and use type annotations.
- Prefer simple, functional code, isolate the non-functional part (e.g. to the CLI).
- Even with YAGNI, prefer code that is easy to change and extend in the future.

## Test instructions
- Run `pytest tests` to execute the test suite.
- Check if the newly added code is covered by inspecting the code coverage report.

## PR instructions
- Summarize changes and list tests run in PR descriptions.
- If the solution is non-trivial, the PR description should elaborate on why it was chosen and not something else.
