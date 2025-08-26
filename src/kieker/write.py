import logging
import sqlite3
from pathlib import Path
from typing import Sequence

from .parse import ParseModuleTask
from .task import Task


logger = logging.getLogger()


def ensure_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(sql)


def delete_modules(conn: sqlite3.Connection, module_ids: Sequence[int]) -> None:
    for mid in module_ids:
        conn.execute("DELETE FROM modules WHERE id=?", (mid,))


class WriteToDbTask(Task):
    """Persist the results of a ParseModuleTask into a SQLite database."""

    def __init__(
        self, task: ParseModuleTask, conn: sqlite3.Connection, version: str
    ) -> None:
        super().__init__()
        self.task = task
        self.conn = conn
        self.version = version

    def run(self) -> None:
        if self.task.module_info is None:
            raise RuntimeError("Parse task did not produce module_info.")
        conn = self.conn

        module_id = self._insert_module(conn)
        class_id_by_qname = self._insert_classes(conn, module_id)
        func_id_by_qname = self._insert_functions(conn, module_id, class_id_by_qname)
        self._insert_parameters(conn, func_id_by_qname)
        self._insert_decorators(conn, class_id_by_qname, func_id_by_qname)
        self._insert_imports(conn, module_id)
        self._insert_inheritance(conn, class_id_by_qname)
        self._insert_calls(conn, func_id_by_qname)
        self._insert_function_metrics(conn, func_id_by_qname)

    def _insert_module(self, conn: sqlite3.Connection) -> int:
        mi = self.task.module_info
        assert mi is not None
        rft = self.task.read_file_task
        file_hash = rft.hash
        assert file_hash is not None, "Module info must have a file hash"
        size = rft.size_bytes
        mtime = rft.mtime_ns
        conn.execute(
            """
            INSERT INTO modules (module, file, file_hash, size_bytes, mtime_ns, kieker_version, is_external)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(module) DO UPDATE SET
              file           = excluded.file,
              file_hash      = excluded.file_hash,
              size_bytes     = excluded.size_bytes,
              mtime_ns       = excluded.mtime_ns,
              kieker_version = excluded.kieker_version,
              is_external    = excluded.is_external
            """,
            (mi.module, mi.file, file_hash, size, mtime, self.version, 0),
        )
        row = conn.execute(
            "SELECT id FROM modules WHERE module = ?", (mi.module,)
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
            conn.execute(
                """
                INSERT INTO functions
                (module_id, class_id, name, qualified_name, is_method, is_staticmethod, is_classmethod, is_property, is_async, file, start_line, start_col, end_line, end_col, body_text, def_text, property_kind, docstring)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(module_id, qualified_name) DO UPDATE SET
                  class_id=excluded.class_id,
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
                  body_text=excluded.body_text,
                  def_text=excluded.def_text,
                  property_kind=excluded.property_kind,
                  docstring=excluded.docstring
                """,
                (
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
                    f.body_text,
                    f.def_text,
                    f.property_kind,
                    f.docstring,
                ),
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
            func_id = func_id_by_qname.get(p.function_qname)
            if func_id is None:
                continue
            conn.execute(
                """
                INSERT INTO parameters
                (function_id, name, pos_kind, default_kind, default_repr, annotation_repr)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(function_id, name, pos_kind) DO UPDATE SET
                  default_kind=excluded.default_kind,
                  default_repr=excluded.default_repr,
                  annotation_repr=excluded.annotation_repr
                """,
                (
                    func_id,
                    p.name,
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
        for d in self.task.decorators:
            target_id = None
            target_kind = "function"
            target_id = func_id_by_qname.get(d.target_qname)
            if target_id is None:
                target_id = class_id_by_qname.get(d.target_qname)
                target_kind = "class"
            if target_id is None:
                continue
            conn.execute(
                """
                INSERT INTO decorators
                (target_kind, target_id, name_repr, file, start_line, start_col, end_line, end_col)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_kind,
                    target_id,
                    d.name_repr,
                    d.location.file,
                    d.location.start_line,
                    d.location.start_col,
                    d.location.end_line,
                    d.location.end_col,
                ),
            )

    def _insert_imports(self, conn: sqlite3.Connection, module_id: int) -> None:
        for imp in self.task.imports:
            conn.execute(
                """
                INSERT INTO imports
                (module_id, imported, alias, is_from_import, file, start_line, start_col, end_line, end_col)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    module_id,
                    imp.imported,
                    imp.alias,
                    int(imp.is_from_import),
                    imp.location.file,
                    imp.location.start_line,
                    imp.location.start_col,
                    imp.location.end_line,
                    imp.location.end_col,
                ),
            )

    def _insert_inheritance(
        self, conn: sqlite3.Connection, class_id_by_qname: dict[str, int]
    ) -> None:
        for inh in self.task.inheritance:
            subclass_id = class_id_by_qname.get(inh.subclass_qname)
            if subclass_id is None:
                continue
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
        for call in self.task.calls:
            caller_id = func_id_by_qname.get(call.caller_qname)
            if caller_id is None:
                continue
            conn.execute(
                """
                INSERT INTO calls
                (caller_id, callee_repr, file, start_line, start_col, end_line, end_col)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    caller_id,
                    call.callee_repr,
                    call.location.file,
                    call.location.start_line,
                    call.location.start_col,
                    call.location.end_line,
                    call.location.end_col,
                ),
            )

    def _insert_function_metrics(
        self, conn: sqlite3.Connection, func_id_by_qname: dict[str, int]
    ) -> None:
        for m in self.task.function_metrics:
            func_id = func_id_by_qname.get(m.function_qname)
            if func_id is None:
                continue
            conn.execute(
                """
                INSERT INTO function_metrics
                (function_id, lines_of_code, cyclomatic)
                VALUES (?, ?, ?)
                ON CONFLICT(function_id) DO UPDATE SET
                  lines_of_code=excluded.lines_of_code,
                  cyclomatic=excluded.cyclomatic
                """,
                (func_id, m.lines_of_code, m.cyclomatic),
            )
