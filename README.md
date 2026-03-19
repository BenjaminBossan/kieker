# Kieker

Query your Python codebase like a database.

This project parses Python source files into a structured SQLite database, so you can write SQL queries against modules, classes, functions, parameters, decorators, imports, inheritance, attributes, calls, and metrics (LOC, cyclomatic complexity, etc.). The main intent is to provide a smarter and more economic code exploration tool for agentic coding that is easy to pick up for an LLM because it is just SQL.

## Example

Here is a short example that shows how to check out a code base, create a database for it, and then run queries against it.

After installing kieker, first check out the repository and create the database:

```sh
cd /tmp
git clone --depth 1 --branch v1.2.0 https://github.com/skorch-dev/skorch.git
cd skorch
kieker create skorch/ --exclude skorch/tests -o result.sqlite -v -j4
```

Then run the query against the db:

```sh
sqlite3 -header -column result.sqlite "SELECT f.file, c.start_line call_line, f.start_line fn_start, f.end_line fn_end, f.qualified_name fn_name
FROM calls c
JOIN functions f ON f.id = c.caller_id
WHERE c.callee_repr = 'np.asarray'
ORDER BY f.file, f.start_line;"
```

This should show:

```
file                              call_line  fn_start  fn_end  fn_name                                           
--------------------------------  ---------  --------  ------  --------------------------------------------------
/tmp/skorch/skorch/classifier.py  103        98        118     classifier.NeuralNetClassifier.classes_           
/tmp/skorch/skorch/helper.py      267        262       268     helper.SliceDataset.__array__                     
/tmp/skorch/skorch/helper.py      268        262       268     helper.SliceDataset.__array__                     
/tmp/skorch/skorch/hf.py          61         46        64      hf._HuggingfaceTokenizerBase.get_feature_names_out
/tmp/skorch/skorch/hf.py          148        126       148     hf._HuggingfaceTokenizerBase.inverse_transform    
/tmp/skorch/skorch/hf.py          183        150       183     hf._HuggingfaceTokenizerBase.tokenize             
/tmp/skorch/skorch/utils.py       150        127       164     utils.to_numpy    
```

More examples [here](https://github.com/BenjaminBossan/kieker/blob/main/examples/usage-example.md).

## Features

- Parse Python code into a normalized SQLite schema.
- Store detailed information about:
  - Modules (with file path, size, mtime, hash and parser version for change detection)
  - Classes (name, qualified name, location, body, docstring)
  - Functions (decorators, parameters, metrics, body text, docstring)
  - Imports, inheritance edges, calls
- Query your codebase with SQL, e.g. to:
  - find the function defintion of `foobar`
  - find which functions call `foobar`
  - list all classes inheriting from `MyBaseClass`
  - find long functions without docstring
  - find functions with many parameters
  - find decorated functions or classes
- CLI tool to create databases, explore example queries, and show a project map.

## Installation

TODO

## Usage

### Create the database

```sh
kieker create src/ -o code.sqlite

```

Use multiple processes with `-j`/`--jobs` (defaults to 1; `0` uses all CPUs):

```sh
kieker create src/ -o code.sqlite -j 4
```

This will:

- Traverse files under src/
- Parse them with [LibCST](https://github.com/Instagram/LibCST)
- Write all data into code.sqlite

Subsequent runs update only files whose contents changed. Use `--force` to
re-parse everything from scratch. Use `--dry-run` to see which files would be
analyzed without writing anything.

For agent-friendly planning output, combine `--dry-run` with `--json`:

```sh
kieker create src/ --dry-run --json
```

### Explore example queries

The CLI ships with some predefined queries:

```sh
kieker examples --list
```

Show example 0:

```sh
kieker examples 0
```

For machine-readable output:

```sh
kieker examples --list --json
kieker examples 0 --json
```

### Show a project map

Generate a tree of modules, classes, and functions:

```sh
kieker map code.sqlite
```

For machine-readable output:

```sh
kieker map code.sqlite --json
```

### Run queries yourself

Open the database with the `sqlite3` command line tool or any other tool of your liking and run the quries you're interested in.

## Using kieker with coding agents

The primary motivation for kieker is to give coding agents (Claude Code, Codex, Cursor, etc.) a more efficient way to explore codebases. Instead of many rounds of `grep` + `cat` + `find`, the agent can answer complex structural questions in a single SQL query.

To instruct an agent to use kieker, add instructions to your project's agent configuration file (e.g. `CLAUDE.md` for Claude Code, `AGENTS.md` for Codex). Below is an example you can adapt.

### Example agent instructions

````markdown
## Code exploration

A kieker database is available at `code.sqlite`. Use it as your primary tool
for navigating the codebase. If the database does not exist or is stale, create
or refresh it:

```sh
kieker create src/ -o code.sqlite
```

### When to use kieker instead of grep/find/cat

Use kieker when your question is about **structure or relationships**:
- "Where is function X defined?" — query `functions`
- "What calls function X?" — join `calls` on `functions`
- "What does class Y inherit from?" — query `inheritance`
- "Show me all methods of class Y" — query `functions` with `class_id`
- "Which modules import package Z?" — query `imports`
- "Find long functions without docstrings" — join `functions` with `function_metrics`

Fall back to grep/cat only for **textual searches** that aren't about code structure (e.g. searching inside string literals or comments).

### How to query

Run queries with `sqlite3`:

```sh
sqlite3 -header -column code.sqlite "<SQL>"
```

Before writing queries, inspect the schema to learn what tables and columns are available:

```sh
sqlite3 code.sqlite ".schema"
```

Use `kieker examples --list` for example queries, then adapt them to your needs. The examples are templates — change the WHERE clauses, add JOINs, and combine tables to answer the specific question at hand.

### Workflow tips

- **Compose queries freely.** The schema is a normalized relational database. Any JOIN that makes sense in SQL is valid. Do not limit yourself to the examples — write the query that answers your question.
- **Use `def_text` to read code.** Instead of `cat file.py | sed -n '10,30p'`, query `SELECT def_text FROM functions WHERE qualified_name LIKE '%my_func'`. This returns exactly the function body with no manual line-range math.
- **Chain queries.** Use the output of one query (e.g. a `qualified_name`) as input to the next. For example: find a class, then find all calls within its methods, then read the callee's source.
- **Re-query after edits.** If you modify source files, run `kieker create src/ -o code.sqlite` again — it only re-parses changed files.
- **Prefer JSON when a command is feeding another tool.** `kieker examples --json`, `kieker map --json`, and `kieker create --dry-run --json` are easier for agents to consume reliably than formatted text.
````

## Limitations

- Python is highly dynamic; this MVP only supports static analysis of AST/CST. Dynamic constructs like `getattr(obj, name)` or runtime code generation are not resolved.
- Only Python is supported for now.
- Duplicates (e.g. multiple defs with the same name in conditionals) are collapsed with last-write-wins semantics; warnings are logged.
- Refactoring (writing code changes) is not supported in the MVP — this is strictly a read/query tool.

## Development

Run formatting and type checks:

```sh
make checks
```

Run tests:

```sh
pytest tests
```
