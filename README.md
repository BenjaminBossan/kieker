# Kieker

Query your Python codebase like a database.

This project parses Python source files into a structured SQLite database, so you can write SQL queries against modules, classes, functions, parameters, decorators, imports, inheritance, calls, and metrics (LOC, cyclomatic complexity, etc.). The main intent is to provide a smarter and more economic code exploration tool for agentic coding that is easy to pick up for an LLM because it is just SQL.

## Features

- Parse Python code into a normalized SQLite schema.
- Store detailed information about:
  - Modules (with file paths + file hash for change detection)
  - Classes (name, qualified name, location, body, docstring)
  - Functions (decorators, parameters, metrics, body text, docstring)
  - Imports, inheritance edges, calls
- Query your codebase with SQL:
  - Which functions call `foo.bar`?
  - List all classes inheriting from `framework.Repository`.
  - Find functions longer than 50 lines with no docstring.
- CLI tool to create databases and explore example queries.

## Installation

TODO

## Usage

### Create the database

python cli.py create src/ --root src -o code.sqlite

This will:

- Traverse files under src/
- Parse them with [LibCST](https://github.com/Instagram/LibCST)
- Write all data into code.sqlite

Use `--dry-run` to see which files would be analyzed without writing anything.

### Explore example queries

The CLI ships with some predefined queries:

```sh
python cli.py examples --list
```

Show example 1:

```sh
python cli.py examples 1
```

### Run queries yourself

Open the database with the `sqlite3` command line tool or any other tool of your liking and run the quries you're interested in.

## Limitations

- Python is highly dynamic; this MVP only supports static analysis of AST/CST. Dynamic constructs like `getattr(obj, name)` or runtime code generation are not resolved.
- Only Python is supported for now.
- Duplicates (e.g. multiple defs with the same name in conditionals) are collapsed with last-write-wins semantics; warnings are logged.
- Refactoring (writing code changes) is not supported in the MVP — this is strictly a read/query tool.

## Development

```sh
mypy --strict src/
ruff check src/
ruff format src/
```
