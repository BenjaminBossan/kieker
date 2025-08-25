PRAGMA foreign_keys = ON;

-- Modules/files are minimal in this MVP (one module per file best-effort)

CREATE TABLE IF NOT EXISTS modules (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  module           TEXT NOT NULL,
  file             TEXT NOT NULL,
  file_hash        TEXT NOT NULL,
  is_external      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS classes (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  module_id        INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
  name             TEXT NOT NULL,
  qualified_name   TEXT NOT NULL,
  file             TEXT NOT NULL,
  start_line       INTEGER NOT NULL,
  start_col        INTEGER NOT NULL,
  end_line         INTEGER NOT NULL,
  end_col          INTEGER NOT NULL,
  body_text        TEXT NOT NULL,
  def_text         TEXT NOT NULL,
  docstring        TEXT
);

CREATE TABLE IF NOT EXISTS functions (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  module_id        INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
  class_id         INTEGER REFERENCES classes(id) ON DELETE CASCADE,
  name             TEXT NOT NULL,
  qualified_name   TEXT NOT NULL,
  is_method        INTEGER NOT NULL,
  is_staticmethod  INTEGER NOT NULL,
  is_classmethod   INTEGER NOT NULL,
  is_property      INTEGER NOT NULL,
  is_async         INTEGER NOT NULL,
  file             TEXT NOT NULL,
  start_line       INTEGER NOT NULL,
  start_col        INTEGER NOT NULL,
  end_line         INTEGER NOT NULL,
  end_col          INTEGER NOT NULL,
  body_text        TEXT NOT NULL,
  def_text         TEXT NOT NULL,
  property_kind    TEXT,
  docstring        TEXT
);

CREATE TABLE IF NOT EXISTS parameters (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  function_id      INTEGER NOT NULL REFERENCES functions(id) ON DELETE CASCADE,
  name             TEXT NOT NULL,
  pos_kind         TEXT NOT NULL,              -- posonly | pos_or_kw | var_pos | kwonly | var_kw
  default_kind     TEXT NOT NULL,              -- none | expr | ellipsis
  default_repr     TEXT,
  annotation_repr  TEXT
);

CREATE TABLE IF NOT EXISTS decorators (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  target_kind      TEXT NOT NULL,              -- function | class
  target_id        INTEGER NOT NULL,           -- FK to functions.id or classes.id (enforced by code)
  name_repr        TEXT NOT NULL,
  file             TEXT NOT NULL,
  start_line       INTEGER NOT NULL,
  start_col        INTEGER NOT NULL,
  end_line         INTEGER NOT NULL,
  end_col          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS imports (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  module_id        INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
  imported         TEXT NOT NULL,
  alias            TEXT,
  is_from_import   INTEGER NOT NULL,
  file             TEXT NOT NULL,
  start_line       INTEGER NOT NULL,
  start_col        INTEGER NOT NULL,
  end_line         INTEGER NOT NULL,
  end_col          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS inheritance (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  subclass_id      INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  superclass_name  TEXT NOT NULL,
  file             TEXT NOT NULL,
  start_line       INTEGER NOT NULL,
  start_col        INTEGER NOT NULL,
  end_line         INTEGER NOT NULL,
  end_col          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS calls (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  caller_id        INTEGER NOT NULL REFERENCES functions(id) ON DELETE CASCADE,
  callee_repr      TEXT NOT NULL,
  file             TEXT NOT NULL,
  start_line       INTEGER NOT NULL,
  start_col        INTEGER NOT NULL,
  end_line         INTEGER NOT NULL,
  end_col          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS function_metrics (
  function_id      INTEGER PRIMARY KEY REFERENCES functions(id) ON DELETE CASCADE,
  lines_of_code    INTEGER NOT NULL,
  cyclomatic       INTEGER NOT NULL
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_modules_module ON modules(module);
CREATE INDEX IF NOT EXISTS idx_functions_qname  ON functions(qualified_name);
CREATE INDEX IF NOT EXISTS idx_classes_qname    ON classes(qualified_name);
CREATE INDEX IF NOT EXISTS idx_calls_caller     ON calls(caller_id);
CREATE INDEX IF NOT EXISTS idx_imports_module   ON imports(module_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_classes_mod_qname
  ON classes(module_id, qualified_name);

CREATE UNIQUE INDEX IF NOT EXISTS uq_functions_mod_qname
  ON functions(module_id, qualified_name);

CREATE UNIQUE INDEX IF NOT EXISTS uq_parameters_func_name_kind
  ON parameters(function_id, name, pos_kind);

CREATE UNIQUE INDEX IF NOT EXISTS uq_inheritance_sub_super
  ON inheritance(subclass_id, superclass_name);

CREATE UNIQUE INDEX IF NOT EXISTS uq_modules_module
  ON modules(module);
