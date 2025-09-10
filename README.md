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

### Explore example queries

The CLI ships with some predefined queries:

```sh
kieker examples --list
```

Show example 0:

```sh
kieker examples 0
```

### Show a project map

Generate a tree of modules, classes, and functions:

```sh
kieker map code.sqlite
```

### Run queries yourself

Open the database with the `sqlite3` command line tool or any other tool of your liking and run the quries you're interested in.

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
