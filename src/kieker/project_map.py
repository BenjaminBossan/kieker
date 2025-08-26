import sqlite3
from dataclasses import dataclass


@dataclass
class FunctionEntry:
    name: str
    file: str
    line: int
    col: int


@dataclass
class ClassEntry:
    name: str
    file: str
    line: int
    methods: list[FunctionEntry]
    col: int


@dataclass
class ModuleEntry:
    name: str
    file: str
    classes: list[ClassEntry]
    functions: list[FunctionEntry]


def create_project_map(conn: sqlite3.Connection) -> list[ModuleEntry]:
    cur = conn.cursor()
    modules: list[ModuleEntry] = []
    module_rows = cur.execute(
        """SELECT id, module, file
        FROM modules
        ORDER BY module"""
    ).fetchall()

    for module_id, module_name, module_file in module_rows:
        classes: list[ClassEntry] = []
        class_rows = cur.execute(
            """SELECT id, name, file, start_line, start_col
            FROM classes
            WHERE module_id = ?
            ORDER BY start_line""",
            (module_id,),
        ).fetchall()

        for class_id, class_name, class_file, class_line, class_col in class_rows:
            methods: list[FunctionEntry] = []
            method_rows = cur.execute(
                """SELECT name, file, start_line, start_col
                FROM functions
                WHERE class_id = ?
                ORDER BY start_line""",
                (class_id,),
            ).fetchall()

            for f_name, f_file, f_line, f_col in method_rows:
                methods.append(
                    FunctionEntry(name=f_name, file=f_file, line=f_line, col=f_col)
                )

            classes.append(
                ClassEntry(
                    name=class_name,
                    file=class_file,
                    line=class_line,
                    col=class_col,
                    methods=methods,
                )
            )

        functions: list[FunctionEntry] = []
        function_rows = cur.execute(
            """SELECT name, file, start_line, start_col
            FROM functions
            WHERE module_id = ? AND class_id IS NULL
            ORDER BY start_line""",
            (module_id,),
        ).fetchall()

        for f_name, f_file, f_line, f_col in function_rows:
            functions.append(
                FunctionEntry(name=f_name, file=f_file, line=f_line, col=f_col)
            )

        modules.append(
            ModuleEntry(
                name=module_name,
                file=module_file,
                classes=classes,
                functions=functions,
            )
        )
    return modules
