import argparse
import logging
import sqlite3
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import kieker
from .ingest import ReadFileTask, gather_read_file_tasks
from .parse import ParseModuleTask
from .task import TaskRunner
from .write import WriteToDbTask, delete_modules, ensure_schema
from .project_map import create_project_map


logger = logging.getLogger("sql-over-code")
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

EXAMPLES: list[dict[str, str]] = [
    {
        "title": "Print function definition and location of function called foobar",
        "sql": textwrap.dedent(
            """
            SELECT file, start_line, end_line, def_text
            FROM functions
            WHERE qualified_name like '%foobar';
            """
        ).strip(),
    },
    {
        "title": "List function names and locations of functions that call foo.bar",
        "sql": textwrap.dedent(
            """
            SELECT f.file, f.start_line, f.end_line, f.qualified_name
            FROM calls c
            JOIN functions f ON f.id = c.caller_id
            WHERE c.callee_repr = 'foo.bar'
            ORDER BY f.file, f.start_line;
            """
        ).strip(),
    },
    {
        "title": "Functions longer than 50 lines and missing a docstring",
        "sql": textwrap.dedent(
            """
            SELECT f.qualified_name, fm.lines_of_code
            FROM functions f
            JOIN function_metrics fm ON fm.function_id = f.id
            WHERE fm.lines_of_code > 50
              AND (f.docstring IS NULL OR f.docstring = '')
            ORDER BY fm.lines_of_code DESC;
            """
        ).strip(),
    },
    {
        "title": "Count functions per module",
        "sql": textwrap.dedent(
            """
            SELECT m.module, COUNT(f.id) AS function_count
            FROM modules m
            JOIN functions f ON f.module_id = m.id
            GROUP BY m.module
            ORDER BY function_count DESC;
            """
        ).strip(),
    },
    {
        "title": "List the location and name of all classes that inherit from class 'Foobar'",
        "sql": textwrap.dedent(
            """
            SELECT c.name AS subclass_name,
              c.file,
              c.start_line,
              c.end_line,
              c.qualified_name
            FROM classes c
            JOIN inheritance i ON i.subclass_id = c.id
            WHERE i.superclass_name = 'Foobar'
            ORDER BY c.file, c.start_line;
            """
        ).strip(),
    },
    {
        "title": "Find functions with highest number of parameters",
        "sql": textwrap.dedent(
            """
            WITH param_counts AS (
              SELECT p.function_id, COUNT(*) AS nparams
              FROM parameters p
              GROUP BY p.function_id
            )
            SELECT f.qualified_name, nparams
            FROM param_counts pc
            JOIN functions f ON f.id = pc.function_id
            WHERE pc.nparams >= 8
            ORDER BY nparams DESC, f.qualified_name
            LIMIT 10;
            """
        ).strip(),
    },
    {
        "title": "Find all classes and functions using a specific decorator",
        "sql": textwrap.dedent(
            """
            SELECT (CASE d.target_kind WHEN 'class' THEN 'class' ELSE 'function' END) AS kind,
                   (CASE d.target_kind
                      WHEN 'class'    THEN (SELECT qualified_name FROM classes  WHERE id = d.target_id)
                      ELSE                 (SELECT qualified_name FROM functions WHERE id = d.target_id)
                    END) AS target_qname, d.file
            FROM decorators d
            WHERE d.name_repr = 'foobar'
            ORDER BY kind, target_qname;
            """
        ).strip(),
    },
    {
        "title": "Find all modules that import a specific package",
        "sql": textwrap.dedent(
            """
            SELECT m.module, i.imported, i.file, i.start_line
            FROM imports i
            JOIN modules m ON m.id = i.module_id
            WHERE i.imported LIKE 'foobar.%'
            ORDER BY m.module, i.file, i.start_line;
            """
        ).strip(),
    },
]
for idx, row in enumerate(EXAMPLES):
    row["id"] = str(idx)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="kieker", description="SQL-over-Code CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # create
    p_create = sub.add_parser("create", help="Index code and create the SQLite DB.")
    p_create.add_argument(
        "paths", nargs="+", help="Input file(s) or directory/ies to analyze."
    )
    p_create.add_argument(
        "--root",
        "-r",
        action="append",
        help="Package root (repeatable). Defaults to each given path.",
    )
    p_create.add_argument(
        "--exclude",
        "-x",
        action="append",
        default=[],
        help="Exclude directory from ingestion (repeatable).",
    )
    p_create.add_argument(
        "-o", "--output", type=Path, required=True, help="Path to output database."
    )
    p_create.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).with_name("schema.sql"),
        help="Path to schema.sql (defaults next to this CLI).",
    )
    p_create.add_argument(
        "--dry-run",
        action="store_true",
        help="Show files that would be analyzed and exit.",
    )
    p_create.add_argument(
        "--force",
        action="store_true",
        help="Reparse all files regardless of modifications.",
    )
    p_create.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase logging verbosity."
    )
    p_create.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=1,
        help="Number of worker processes (default: 1, 0 uses CPU count).",
    )

    # examples
    p_examples = sub.add_parser(
        "examples", help="List or show predefined examples of SQL queries."
    )
    p_examples.add_argument("id", nargs="?", help="Example ID to print the SQL for.")
    p_examples.add_argument(
        "-l", "--list", action="store_true", help="List available examples."
    )

    # map
    p_map = sub.add_parser("map", help="Print a map of modules, classes and functions.")
    p_map.add_argument("db", type=Path, help="Path to SQLite database file.")
    return parser.parse_args(argv)


def _validate_roots(root_strs: list[str]) -> list[Path]:
    roots = [Path(r).resolve() for r in root_strs]
    bad = [r for r in roots if not r.exists() or not r.is_dir()]
    if bad:
        for b in bad:
            logger.error("Root does not exist or is not a directory: %s", b)
        sys.exit(2)
    return roots


@dataclass
class PlanResult:
    tasks: list[ParseModuleTask]
    delete_ids: list[int]
    added: list[str]
    modified: list[str]
    deleted: list[str]


def create_plan(
    paths: list[Path],
    output: Path,
    roots_str: list[str] | None = None,
    schema: Path | None = None,
    exclude: list[str] | None = None,
    jobs: int = 1,
    force: bool = False,
) -> PlanResult:
    schema = schema or Path(__file__).with_name("schema.sql")
    if roots_str:
        roots = _validate_roots(roots_str)
    else:
        roots = [Path(p).resolve() for p in paths]

    exclude_paths = [Path(x).resolve() for x in (exclude or [])]
    read_tasks = list(gather_read_file_tasks(paths, exclude=exclude_paths))
    runner = TaskRunner(tasks=read_tasks, jobs=jobs)
    runner.run()

    current: dict[str, ReadFileTask] = {}
    for t in read_tasks:
        path = t.filename.as_posix()
        current[path] = t

    existing: dict[str, tuple[int, str, str]] = {}
    if output.exists():
        conn = sqlite3.connect(output)
        try:
            for row in conn.execute(
                "SELECT id, file, file_hash, kieker_version FROM modules"
            ):
                existing[row[1]] = (int(row[0]), row[2], row[3])
        finally:
            conn.close()

    delete_ids: list[int] = []
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []

    for path, task in current.items():
        row = existing.get(path)
        if row is None:
            added.append(path)
        else:
            mod_id, file_hash, ver = row
            if force or task.hash != file_hash or ver != kieker.__version__:
                modified.append(path)
                delete_ids.append(mod_id)

    for path, (mid, _, _) in existing.items():
        if path not in current:
            deleted.append(path)
            delete_ids.append(mid)

    parse_tasks = [ParseModuleTask(current[p], roots) for p in added + modified]
    return PlanResult(
        tasks=parse_tasks,
        delete_ids=delete_ids,
        added=added,
        modified=modified,
        deleted=deleted,
    )


def create(
    paths: list[Path],
    output: Path,
    roots_str: list[str] | None = None,
    schema: Path | None = None,
    exclude: list[str] | None = None,
    jobs: int = 1,
    force: bool = False,
    plan: PlanResult | None = None,
) -> TaskRunner:
    schema = schema or Path(__file__).with_name("schema.sql")
    if plan is None:
        plan = create_plan(
            paths=paths,
            output=output,
            roots_str=roots_str,
            schema=schema,
            exclude=exclude,
            jobs=jobs,
            force=force,
        )
    parse_runner = TaskRunner(tasks=plan.tasks, jobs=jobs)
    parse_runner.run()

    conn = sqlite3.connect(output)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        ensure_schema(conn, schema)
        conn.execute("BEGIN")
        delete_modules(conn, plan.delete_ids)
        for t in plan.tasks:
            WriteToDbTask(t, conn, kieker.__version__).run()
        conn.commit()
    finally:
        conn.close()
    return parse_runner


def cmd_create(args: argparse.Namespace) -> None:
    if args.verbose >= 1:
        logger.setLevel(logging.DEBUG)

    plan = create_plan(
        paths=[Path(p) for p in args.paths],
        output=args.output,
        roots_str=args.root,
        schema=args.schema,
        exclude=args.exclude,
        jobs=args.jobs,
        force=args.force,
    )

    if args.dry_run:
        logger.debug(
            "Plan: %d added, %d modified, %d deleted",
            len(plan.added),
            len(plan.modified),
            len(plan.deleted),
        )
        for p in plan.added:
            logger.debug("  add %s", p)
        for p in plan.modified:
            logger.debug("  mod %s", p)
        for p in plan.deleted:
            logger.debug("  del %s", p)
        return

    task_runner = create(
        paths=[Path(p) for p in args.paths],
        output=args.output,
        roots_str=args.root,
        schema=args.schema,
        exclude=args.exclude,
        jobs=args.jobs,
        force=args.force,
        plan=plan,
    )
    logger.info("Wrote database to %s", args.output)
    for key, summary in task_runner.summary.items():
        logger.debug(
            (
                "%s: %d tasks, %d success, %d failed, %d canceled, user time %.2f "
                "seconds, wall time %.2f seconds"
            ),
            key,
            summary.count,
            summary.success,
            summary.failed,
            summary.canceled,
            summary.user_time,
            summary.wall_time,
        )


def cmd_examples(args: argparse.Namespace) -> None:
    if args.list or args.id is None:
        # List mode
        for ex in EXAMPLES:
            print(f"{ex['id']}. {ex['title']}")
        if args.id is None:
            return

    # Print one example
    ex = next((e for e in EXAMPLES if e["id"] == args.id), {})
    if not ex:
        logger.error("Unknown example id: %s", args.id)
        sys.exit(2)

    print(f"-- Example {ex['id']}: {ex['title']}\n")
    print(ex["sql"])


def cmd_map(args: argparse.Namespace) -> None:
    conn = sqlite3.connect(args.db)
    try:
        modules = create_project_map(conn)
    finally:
        conn.close()

    for module in modules:
        print(f"{module.name}  {module.file}")
        for cls in module.classes:
            indent = "    " + cls.col * " "
            print(f"{indent}class {cls.name}  {cls.file}:{cls.line}")
            for func in cls.methods:
                indent = "    " + func.col * " "
                loc = f"{func.file}:{func.line}"
                print(f"{indent}def {func.name} {loc}")
        for func in module.functions:
            indent = "    " + func.col * " "
            print(f"{indent}def {func.name}  {func.file}:{func.line}")


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.cmd == "create":
        cmd_create(args)
    elif args.cmd == "examples":
        cmd_examples(args)
    elif args.cmd == "map":
        cmd_map(args)
    else:
        raise AssertionError("unreachable")


if __name__ == "__main__":
    main()
