import logging
import sqlite3
from pathlib import Path
from typing import Optional

from .task import Task
from .parse import ParseModuleTask


logger = logging.getLogger()


class WriteToDbTask(Task):
    """
    Persist the results of a ParseModuleTask into a SQLite database.

    - Loads schema from a separate SQL file (schema_path).
    - Creates/overwrites the target DB file depending on `override`.
    - Inserts one module row and all related rows (classes, functions, ...).
    """

    def __init__(
        self,
        task: ParseModuleTask,
        output: Path,
        schema_path: Path = Path(".") / "schema.sql",
        override: bool = True,
    ) -> None:
        super().__init__()
        self.task = task
        self.output = output
        self.schema_path = schema_path
        self.override = override
        self._validate_output()

    def _validate_output(self) -> None:
        if self.output.exists():
            if not self.override:
                raise FileExistsError(
                    f"Output database already exists and override=False: {self.output}"
                )
            # If overriding, remove existing file to ensure a clean schema apply.
            self.output.unlink()

        # Ensure parent directory exists
        self.output.parent.mkdir(parents=True, exist_ok=True)

        if not self.schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {self.schema_path}")

    def _apply_schema(self, conn: sqlite3.Connection) -> None:
        sql = self.schema_path.read_text(encoding="utf-8")
        conn.executescript(sql)

    def run(self) -> None:
        # Ensure parse task has results
        # (If the caller already ran it, this is idempotent.)
        self.task.run()

        if self.task.module_info is None:
            raise RuntimeError("Parse task did not produce module_info.")

        conn = sqlite3.connect(self.output)
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            self._apply_schema(conn)

            # Insert module
            module_id = self._insert_module(conn)

            # Insert classes
            class_id_by_qname = self._insert_classes(conn, module_id)

            # Insert functions
            func_id_by_qname = self._insert_functions(
                conn, module_id, class_id_by_qname
            )

            # Parameters
            self._insert_parameters(conn, func_id_by_qname)

            # Decorators (function + class)
            self._insert_decorators(conn, class_id_by_qname, func_id_by_qname)

            # Imports
            self._insert_imports(conn, module_id)

            # Inheritance
            self._insert_inheritance(conn, class_id_by_qname)

            # Calls
            self._insert_calls(conn, func_id_by_qname)

            # Metrics
            self._insert_function_metrics(conn, func_id_by_qname)

            conn.commit()
        finally:
            conn.close()

    def _insert_module(self, conn: sqlite3.Connection) -> int:
        mi = self.task.module_info
        assert mi is not None
        file_hash = self.task.read_file_task.hash
        assert file_hash is not None, "Module info must have a file hash"
        conn.execute(
            """
            INSERT INTO modules (package, file, file_hash, is_external)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(package) DO UPDATE SET
              file       = excluded.file,
              file_hash  = excluded.file_hash,
              is_external= excluded.is_external
            """,
            (mi.package, mi.file, file_hash, 0),
        )
        # Fetch (or re-fetch) the id
        row = conn.execute(
            "SELECT id FROM modules WHERE package = ?", (mi.package,)
        ).fetchone()
        return int(row[0])

    def _insert_classes(
        self, conn: sqlite3.Connection, module_id: int
    ) -> dict[str, int]:
        class_id_by_qname: dict[str, int] = {}
        rows = []
        for c in self.task.classes:
            rows.append(
                (
                    module_id,
                    c.name,
                    c.qualified_name,
                    c.location.file,
                    c.location.start_line,
                    c.location.start_col,
                    c.location.end_line,
                    c.location.end_col,
                    c.def_text,
                    c.body_text,
                    c.docstring,
                )
            )

        if not rows:
            return class_id_by_qname

        # last-write-wins; log when we overwrite
        for r in rows:
            mod_id, name, qname, *_ = r
            # exists?
            cur = conn.execute(
                "SELECT id FROM classes WHERE module_id=? AND qualified_name=?",
                (mod_id, qname),
            )
            existing = cur.fetchone()
            if existing:
                logger.warning(
                    "Duplicate class %s in module %s → overwriting (id=%s)",
                    qname,
                    mod_id,
                    existing[0],
                )

            conn.execute(
                """
                INSERT INTO classes
                (module_id, name, qualified_name, file, start_line, start_col, end_line, end_col, def_text, body_text, docstring)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(module_id, qualified_name) DO UPDATE SET
                  name=excluded.name,
                  file=excluded.file,
                  start_line=excluded.start_line,
                  start_col=excluded.start_col,
                  end_line=excluded.end_line,
                  end_col=excluded.end_col,
                  def_text=excluded.def_text,
                  body_text=excluded.body_text,
                  docstring=excluded.docstring
                """,
                r,
            )

        # map qname → id
        for cid, qn in conn.execute(
            "SELECT id, qualified_name FROM classes WHERE module_id=?", (module_id,)
        ):
            class_id_by_qname[qn] = int(cid)
        return class_id_by_qname

    def _insert_functions(
        self,
        conn: sqlite3.Connection,
        module_id: int,
        class_id_by_qname: dict[str, int],
    ) -> dict[str, int]:
        func_id_by_qname: dict[str, int] = {}
        for f in self.task.functions:
            class_id = None
            if f.is_method:
                class_qname = f.qualified_name.rsplit(".", 1)[0]
                class_id = class_id_by_qname.get(class_qname)

            payload = (
                module_id,
                class_id,
                f.name,
                f.qualified_name,
                int(f.is_method),
                int(f.is_staticmethod),
                int(f.is_classmethod),
                int(f.is_property),
                int(f.is_async),
                f.location.file,
                f.location.start_line,
                f.location.start_col,
                f.location.end_line,
                f.location.end_col,
                f.def_text,
                f.body_text,
                f.docstring,
            )

            # log on duplicate
            cur = conn.execute(
                "SELECT id FROM functions WHERE module_id=? AND qualified_name=?",
                (module_id, f.qualified_name),
            )
            existing = cur.fetchone()
            if existing:
                logger.warning(
                    "Duplicate function %s in module %s → overwriting (id=%s)",
                    f.qualified_name,
                    module_id,
                    existing[0],
                )

            conn.execute(
                """
                INSERT INTO functions
                (module_id, class_id, name, qualified_name, is_method, is_staticmethod, is_classmethod,
                 is_property, is_async, file, start_line, start_col, end_line, end_col, def_text, body_text, docstring)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(module_id, qualified_name) DO UPDATE SET
                  class_id=excluded.class_id,
                  name=excluded.name,
                  is_method=excluded.is_method,
                  is_staticmethod=excluded.is_staticmethod,
                  is_classmethod=excluded.is_classmethod,
                  is_property=excluded.is_property,
                  is_async=excluded.is_async,
                  file=excluded.file,
                  start_line=excluded.start_line,
                  start_col=excluded.start_col,
                  end_line=excluded.end_line,
                  end_col=excluded.end_col,
                  def_text=excluded.def_text,
                  body_text=excluded.body_text,
                  docstring=excluded.docstring
                """,
                payload,
            )

        for fid, qn in conn.execute(
            "SELECT id, qualified_name FROM functions WHERE module_id=?", (module_id,)
        ):
            func_id_by_qname[qn] = int(fid)
        return func_id_by_qname

    def _insert_parameters(
        self, conn: sqlite3.Connection, func_id_by_qname: dict[str, int]
    ) -> None:
        for p in self.task.parameters:
            fid = func_id_by_qname.get(p.function_qname)
            if fid is None:
                continue
            name_str = (
                p.name
                if isinstance(p.name, str)
                else getattr(p.name, "value", str(p.name))
            )

            # Log if duplicate
            cur = conn.execute(
                "SELECT 1 FROM parameters WHERE function_id=? AND name=? AND pos_kind=?",
                (fid, name_str, p.pos_kind),
            )
            if cur.fetchone():
                logger.warning(
                    "Duplicate parameter %s (%s) for function_id=%s → overwriting",
                    name_str,
                    p.pos_kind,
                    fid,
                )

            conn.execute(
                """
                INSERT INTO parameters (function_id, name, pos_kind, default_kind, default_repr, annotation_repr)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(function_id, name, pos_kind) DO UPDATE SET
                  default_kind=excluded.default_kind,
                  default_repr=excluded.default_repr,
                  annotation_repr=excluded.annotation_repr
                """,
                (
                    fid,
                    name_str,
                    p.pos_kind,
                    p.default_kind,
                    p.default_repr,
                    p.annotation_repr,
                ),
            )

    def _insert_decorators(
        self,
        conn: sqlite3.Connection,
        class_id_by_qname: dict[str, int],
        func_id_by_qname: dict[str, int],
    ) -> None:
        rows = []
        for d in self.task.decorators:
            target_kind: Optional[str] = None
            target_id: Optional[int] = func_id_by_qname.get(d.target_qname)
            if target_id is not None:
                target_kind = "function"
            else:
                target_id = class_id_by_qname.get(d.target_qname)
                if target_id is not None:
                    target_kind = "class"

            if target_kind is None or target_id is None:
                continue  # skip unknown targets in MVP

            rows.append(
                (
                    target_kind,
                    target_id,
                    d.name_repr,
                    d.location.file,
                    d.location.start_line,
                    d.location.start_col,
                    d.location.end_line,
                    d.location.end_col,
                )
            )
        if rows:
            conn.executemany(
                """
                INSERT INTO decorators
                (target_kind, target_id, name_repr, file, start_line, start_col, end_line, end_col)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def _insert_imports(self, conn: sqlite3.Connection, module_id: int) -> None:
        rows = []
        for im in self.task.imports:
            rows.append(
                (
                    module_id,
                    im.imported,
                    im.alias,
                    1 if im.is_from_import else 0,
                    im.location.file,
                    im.location.start_line,
                    im.location.start_col,
                    im.location.end_line,
                    im.location.end_col,
                )
            )
        if rows:
            conn.executemany(
                """
                INSERT INTO imports
                (module_id, imported, alias, is_from_import, file, start_line, start_col, end_line, end_col)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def _insert_inheritance(
        self, conn: sqlite3.Connection, class_id_by_qname: dict[str, int]
    ) -> None:
        for inh in self.task.inheritance:
            subclass_id = class_id_by_qname.get(inh.subclass_qname)
            if subclass_id is None:
                continue
            cur = conn.execute(
                "SELECT 1 FROM inheritance WHERE subclass_id=? AND superclass_name=?",
                (subclass_id, inh.superclass_name),
            )
            if cur.fetchone():
                logger.warning(
                    "Duplicate inheritance %s -> %s → overwriting",
                    inh.subclass_qname,
                    inh.superclass_name,
                )

            conn.execute(
                """
                INSERT INTO inheritance (subclass_id, superclass_name, file, start_line, start_col, end_line, end_col)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(subclass_id, superclass_name) DO UPDATE SET
                  file=excluded.file,
                  start_line=excluded.start_line,
                  start_col=excluded.start_col,
                  end_line=excluded.end_line,
                  end_col=excluded.end_col
                """,
                (
                    subclass_id,
                    inh.superclass_name,
                    inh.location.file,
                    inh.location.start_line,
                    inh.location.start_col,
                    inh.location.end_line,
                    inh.location.end_col,
                ),
            )

    def _insert_calls(
        self, conn: sqlite3.Connection, func_id_by_qname: dict[str, int]
    ) -> None:
        rows = []
        for call in self.task.calls:
            caller_id = func_id_by_qname.get(call.caller_qname)
            if caller_id is None:
                # module-level call (caller_qname like "<module>") → skip for MVP or model separately
                continue
            rows.append(
                (
                    caller_id,
                    call.callee_repr,
                    call.location.file,
                    call.location.start_line,
                    call.location.start_col,
                    call.location.end_line,
                    call.location.end_col,
                )
            )
        if rows:
            conn.executemany(
                """
                INSERT INTO calls
                (caller_id, callee_repr, file, start_line, start_col, end_line, end_col)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def _insert_function_metrics(
        self, conn: sqlite3.Connection, func_id_by_qname: dict[str, int]
    ) -> None:
        for m in self.task.function_metrics:
            fid = func_id_by_qname.get(m.function_qname)
            if fid is None:
                continue

            # Log if we’re overwriting
            cur = conn.execute(
                "SELECT 1 FROM function_metrics WHERE function_id=?", (fid,)
            )
            if cur.fetchone():
                logger.warning(
                    "Duplicate metrics for function %s (id=%s) → overwriting",
                    m.function_qname,
                    fid,
                )

            conn.execute(
                """
                INSERT INTO function_metrics (function_id, lines_of_code, cyclomatic)
                VALUES (?, ?, ?)
                ON CONFLICT(function_id) DO UPDATE SET
                  lines_of_code=excluded.lines_of_code,
                  cyclomatic=excluded.cyclomatic
                """,
                (fid, m.lines_of_code, m.cyclomatic),
            )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(task={self.task}, output={self.output})"
