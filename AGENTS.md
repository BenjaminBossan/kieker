# AGENTS Instructions

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
