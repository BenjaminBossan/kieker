"""TODO:

- [ ] Uniqueness constraint for identifiers (e.g., function names) is not always
  enforced. E.g. function definition depending on value:
  if x > 0: def f(): pass; else: def f(): pass
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Sequence

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider, ParentNodeProvider

from .task import Task
from .ingest import ReadFileTask


@dataclass(frozen=True)
class Location:
    file: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int


@dataclass
class ModuleInfo:
    module: str  # dotted, best-effort from path
    file: str  # path string
    is_external: bool = False  # always False for parsed source
    primary_file: Optional[str] = None


@dataclass
class ClassInfo:
    name: str
    qualified_name: str  # <module>.<Class>
    location: Location
    def_text: str
    body_text: str
    docstring: Optional[str] = None


@dataclass
class FunctionInfo:
    name: str
    qualified_name: str  # <module>.<func> or <module>.<Class>.<method>
    is_method: bool
    is_staticmethod: bool
    is_classmethod: bool
    is_property: bool
    is_async: bool
    location: Location
    def_text: str
    body_text: str
    property_kind: Optional[Literal["getter", "setter", "deleter"]]
    docstring: Optional[str] = None


@dataclass
class ParameterInfo:
    function_qname: str
    name: str
    pos_kind: str  # posonly | pos_or_kw | var_pos | kwonly | var_kw
    default_kind: str  # none | expr | ellipsis
    default_repr: Optional[str]  # textual repr
    annotation_repr: Optional[str]


@dataclass
class DecoratorInfo:
    target_qname: str  # function or class qname
    name_repr: str  # as written (unresolved)
    location: Location


@dataclass
class ImportInfo:
    importer_module: str
    imported: str  # as written, dotted text
    alias: Optional[str]
    is_from_import: bool
    location: Location


@dataclass
class InheritanceEdge:
    subclass_qname: str
    superclass_name: str  # as written (unresolved dotted)
    location: Location


@dataclass
class CallInfo:
    caller_qname: str
    callee_repr: str  # syntactic dotted text
    location: Location


@dataclass
class FunctionMetrics:
    function_qname: str
    lines_of_code: int
    cyclomatic: int


def infer_module_name(file: Path, roots: Sequence[Path]) -> str:
    f = file.resolve()
    # choose the most specific root that is an ancestor
    candidates: list[Path] = []
    for r in (Path(r).resolve() for r in roots):
        try:
            _ = f.relative_to(r)
            candidates.append(r)
        except ValueError:
            continue
    if not candidates:
        # best-effort fallback: strip drive and extension, dot-join all parts
        p = f.with_suffix("")
        parts = [p for p in p.parts if p not in (".", "")]
        return ".".join(parts)

    root = max(candidates, key=lambda p: len(p.parts))
    rel = f.relative_to(root)
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts:
        parts[-1] = parts[-1].rsplit(".", 1)[0]  # drop .py
    return ".".join(parts)


def _to_location(filename: str, span: cst.metadata.CodeRange) -> Location:
    return Location(
        file=filename,
        start_line=span.start.line,
        start_col=span.start.column,
        end_line=span.end.line,
        end_col=span.end.column,
    )


def _dotted_name(expr: cst.CSTNode) -> str:
    """
    Convert Name/Attribute/Subscript chains to a dotted string (syntactic).
    Returns None if it can't produce a meaningful dotted name.
    """
    if isinstance(expr, cst.Name):
        return expr.value
    if isinstance(expr, cst.Attribute):
        left = _dotted_name(expr.value)
        right = _dotted_name(expr.attr)
        if left and right:
            return f"{left}.{right}"
        return right or left
    if isinstance(expr, cst.Call):
        # Something like decorator calls: @dataclass(order=True) => "dataclass"
        return _dotted_name(expr.func)
    if isinstance(expr, cst.Subscript):
        # e.g., typing.List[ist[nt] -> "typing.List"
        return _dotted_name(expr.value)
    if isinstance(expr, cst.Attribute):  # already covered; defensive
        return _dotted_name(expr.attr)
    return ""


class _ModuleCollector(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider, ParentNodeProvider)

    def __init__(self, module_name: str, filename: str, module: cst.Module) -> None:
        self.module_name = module_name
        self.filename = filename
        self._module: cst.Module = module

        # Stacks for nesting
        self._class_stack: list[ClassInfo] = []
        self._func_stack: list[FunctionInfo] = []

        # Outputs
        self.module: ModuleInfo = ModuleInfo(
            module=module_name, file=filename, primary_file=filename
        )
        self.classes: list[ClassInfo] = []
        self.functions: list[FunctionInfo] = []
        self.parameters: list[ParameterInfo] = []
        self.decorators: list[DecoratorInfo] = []
        self.imports: list[ImportInfo] = []
        self.inheritance: list[InheritanceEdge] = []
        self.calls: list[CallInfo] = []
        self.function_metrics: list[FunctionMetrics] = []

        # Scratch for metrics (per function cyclomatic)
        self._current_cyclomatic: list[int] = []  # parallel to func stack
        self._function_locs: list[int] = []  # ditto

    def _scope_prefix(self) -> str:
        """
        module[.outer_func[.outer_class[.inner_func...]]]
        Order is: module, then all enclosing functions, then all enclosing classes (in their nesting order).
        """
        parts: list[str] = [self.module_name]
        # functions in order of nesting
        parts.extend(fn.name for fn in self._func_stack)
        # classes in order of nesting
        parts.extend(cls.name for cls in self._class_stack)
        return ".".join(parts)

    def _current_class_qname(self) -> Optional[str]:
        return self._class_stack[-1].qualified_name if self._class_stack else None

    def _current_func_qname(self) -> Optional[str]:
        return self._func_stack[-1].qualified_name if self._func_stack else None

    def _position(self, node: cst.CSTNode) -> cst.metadata.CodeRange:
        return self.get_metadata(PositionProvider, node)

    def visit_Import(self, node: cst.Import) -> None:
        for alias in node.names:
            name = _dotted_name(alias.name)
            if alias.asname is None:
                asname = None
            elif hasattr(alias.asname.name, "value"):
                asname = alias.asname.name.value
            else:
                asname = None
            loc = _to_location(self.filename, self._position(node))
            self.imports.append(
                ImportInfo(
                    importer_module=self.module_name,
                    imported=name,
                    alias=asname,
                    is_from_import=False,
                    location=loc,
                )
            )

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        module = _dotted_name(node.module) if node.module else ""
        if isinstance(node.names, cst.ImportStar):
            # from x import *
            loc = _to_location(self.filename, self._position(node))
            self.imports.append(
                ImportInfo(
                    importer_module=self.module_name,
                    imported=f"{module}.*" if module else "*",
                    alias=None,
                    is_from_import=True,
                    location=loc,
                )
            )
            return
        for alias in node.names:
            name = _dotted_name(alias.name)
            full = f"{module}.{name}" if module else name
            if alias.asname is None:
                asname = None
            elif hasattr(alias.asname.name, "value"):
                asname = alias.asname.name.value
            else:
                asname = None
            loc = _to_location(self.filename, self._position(node))
            self.imports.append(
                ImportInfo(
                    importer_module=self.module_name,
                    imported=full,
                    alias=asname,
                    is_from_import=True,
                    location=loc,
                )
            )

    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        prefix = self._scope_prefix()
        qname = f"{prefix}.{node.name.value}"
        pos = self._position(node)
        doc = node.get_docstring()

        cls = ClassInfo(
            name=node.name.value,
            qualified_name=qname,
            location=_to_location(self.filename, pos),
            docstring=doc,
            def_text="\n" + self._module.code_for_node(node).lstrip(),
            body_text="\n" + self._module.code_for_node(node.body),
        )
        self.classes.append(cls)
        self._class_stack.append(cls)

        # decorators
        for dec in node.decorators:
            dec_name = _dotted_name(dec.decorator)
            self.decorators.append(
                DecoratorInfo(
                    target_qname=qname,
                    name_repr=dec_name,
                    location=_to_location(self.filename, self._position(dec)),
                )
            )

        # bases / inheritance edges
        for base in node.bases:
            base_name = _dotted_name(base.value)
            self.inheritance.append(
                InheritanceEdge(
                    subclass_qname=qname,
                    superclass_name=base_name,
                    location=_to_location(self.filename, self._position(base)),
                )
            )

    def leave_ClassDef(self, node: cst.ClassDef) -> None:
        self._class_stack.pop()

    def _get_code(self, node: Optional[cst.CSTNode]) -> Optional[str]:
        return self._module.code_for_node(node) if node is not None else None

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        prefix = self._scope_prefix()
        base_qname = f"{prefix}.{node.name.value}"
        pos = self._position(node)
        doc = node.get_docstring()

        dec_names = [_dotted_name(d.decorator) for d in node.decorators]
        # Property flags
        is_prop_getter = any(
            n.endswith("property") or n.endswith(".getter") for n in dec_names
        )
        is_prop_setter = any(n.endswith(".setter") for n in dec_names)
        is_prop_deleter = any(n.endswith(".deleter") for n in dec_names)

        property_kind: Optional[Literal["getter", "setter", "deleter"]] = None
        if is_prop_setter:
            property_kind = "setter"
        elif is_prop_deleter:
            property_kind = "deleter"
        elif is_prop_getter:
            property_kind = "getter"
        # Disambiguate only non-getter accessors
        qname = (
            base_qname
            if property_kind in (None, "getter")
            else f"{base_qname}#{property_kind}"
        )

        is_static = any(name.endswith("staticmethod") for name in dec_names)
        is_classmethod = any(name.endswith("classmethod") for name in dec_names)
        is_prop = any(
            name.endswith("property")
            or name.endswith(".setter")
            or name.endswith(".getter")
            for name in dec_names
        )

        fn = FunctionInfo(
            name=node.name.value,
            qualified_name=qname,
            is_method=bool(self._class_stack),  # method iff inside any class scope
            is_staticmethod=is_static,
            is_classmethod=is_classmethod,
            is_property=is_prop,
            is_async=bool(node.asynchronous),
            location=_to_location(self.filename, pos),
            def_text="\n" + self._module.code_for_node(node).lstrip(),
            body_text="\n" + self._module.code_for_node(node.body),
            property_kind=property_kind,
            docstring=doc,
        )
        self.functions.append(fn)
        self._func_stack.append(fn)
        self._current_cyclomatic.append(1)
        self._function_locs.append(max(1, pos.end.line - pos.start.line + 1))

        # record decorators
        for dec, name in zip(node.decorators, dec_names):
            self.decorators.append(
                DecoratorInfo(
                    target_qname=qname,
                    name_repr=name,
                    location=_to_location(self.filename, self._position(dec)),
                )
            )

        # parameters
        def add_params(params: Sequence[cst.CSTNode], kind: str) -> None:
            for p in params:
                # Guard against unexpected node types
                if not isinstance(p, cst.Param):
                    # If something non-standard appears, skip or record minimally
                    continue

                # Default value
                default_node = getattr(p, "default", None)
                if default_node is not None:
                    default_kind = "expr"
                    default_repr = self._get_code(default_node)
                elif isinstance(default_node, cst.Ellipsis):
                    default_kind = "ellipsis"
                    default_repr = "..."
                else:
                    default_kind = "none"
                    default_repr = None

                # Annotation (Param.annotation is a cst.Annotation wrapper)
                ann_wrapper = getattr(p, "annotation", None)
                if isinstance(ann_wrapper, cst.Annotation):
                    annotation_repr = self._get_code(ann_wrapper.annotation)
                else:
                    annotation_repr = None

                self.parameters.append(
                    ParameterInfo(
                        function_qname=qname,
                        name=p.name.value,
                        pos_kind=kind,
                        default_kind=default_kind,
                        default_repr=default_repr,
                        annotation_repr=annotation_repr,
                    )
                )

        ps = node.params
        add_params(ps.params, "pos_or_kw")
        add_params(ps.posonly_params, "posonly")
        add_params(ps.kwonly_params, "kwonly")

        # *args (may be Param or a star slot without annotation)
        if ps.star_arg:
            ann_repr = None
            name = "*"
            if isinstance(ps.star_arg, cst.Param):
                if ps.star_arg.annotation and isinstance(
                    ps.star_arg.annotation, cst.Annotation
                ):
                    ann_repr = self._get_code(ps.star_arg.annotation.annotation)  # TODO
                if ps.star_arg.name:
                    name_ = ps.star_arg.name
                    name = name_.value if isinstance(name_, cst.Name) else name_
                    assert isinstance(name, str), (
                        "Star argument name should be a string"
                    )
            elif isinstance(ps.star_arg, cst.MaybeSentinel):
                name = ps.star_arg.name
                if isinstance(name, cst.Name):
                    name = name.value
                assert isinstance(name, str), "Star argument name should be a string"

            self.parameters.append(
                ParameterInfo(
                    function_qname=qname,
                    name=name,
                    pos_kind="var_pos",
                    default_kind="none",
                    default_repr=None,
                    annotation_repr=ann_repr,
                )
            )

        # **kwargs (may be Param or ParamKwarg)
        if ps.star_kwarg:
            ann_repr = None
            name = ps.star_kwarg.name.value
            assert isinstance(name, str), (
                "Star keyword argument name should be a string"
            )
            if isinstance(ps.star_kwarg, cst.Param) and ps.star_kwarg.annotation:
                ann_repr = self._get_code(ps.star_kwarg.annotation.annotation)  # TODO

            self.parameters.append(
                ParameterInfo(
                    function_qname=qname,
                    name=name,
                    pos_kind="var_kw",
                    default_kind="none",
                    default_repr=None,
                    annotation_repr=ann_repr,
                )
            )

    def leave_FunctionDef(self, node: cst.FunctionDef) -> None:
        # finalize metrics for the function just left
        fn = self._func_stack.pop()
        cyclo = self._current_cyclomatic.pop()
        loc = self._function_locs.pop()
        self.function_metrics.append(
            FunctionMetrics(
                function_qname=fn.qualified_name, lines_of_code=loc, cyclomatic=cyclo
            )
        )

    # Increment on control-flow structures and boolean operators.
    def visit_If(self, node: cst.If) -> Optional[bool]:
        if self._current_cyclomatic:
            self._current_cyclomatic[-1] += 1
        return True

    def visit_For(self, node: cst.For) -> Optional[bool]:
        if self._current_cyclomatic:
            self._current_cyclomatic[-1] += 1
        return True

    def visit_While(self, node: cst.While) -> Optional[bool]:
        if self._current_cyclomatic:
            self._current_cyclomatic[-1] += 1
        return True

    def visit_Try(self, node: cst.Try) -> Optional[bool]:
        if self._current_cyclomatic:
            # try adds 1; each except adds 1
            self._current_cyclomatic[-1] += 1 + len(node.handlers)
        return True

    def visit_With(self, node: cst.With) -> Optional[bool]:
        # Not typically counted, but harmless to keep simple (omit)
        return True

    def visit_BooleanOperation(self, node: cst.BooleanOperation) -> Optional[bool]:
        # Each 'and'/'or' increases complexity by (#operands - 1)
        if self._current_cyclomatic:
            self._current_cyclomatic[-1] += 1
        return True

    def visit_Match(self, node: cst.Match) -> Optional[bool]:
        # Python 3.10 pattern matching: each case adds a path
        if self._current_cyclomatic:
            self._current_cyclomatic[-1] += 1
        return True

    # ---- Calls (syntactic)
    def visit_Call(self, node: cst.Call) -> None:
        callee = _dotted_name(node.func)
        caller_qname = self._current_func_qname() or f"{self.module_name}:<module>"
        self.calls.append(
            CallInfo(
                caller_qname=caller_qname,
                callee_repr=callee,
                location=_to_location(self.filename, self._position(node)),
            )
        )


class ParseModuleTask(Task):
    """
    Parse a single Python module with libcst and collect structured facts.
    """

    def __init__(self, read_file_task: ReadFileTask, roots: Sequence[Path]) -> None:
        super().__init__()
        self.read_file_task = read_file_task
        self.roots = [Path(r).resolve() for r in roots]

        # Results
        self.raw_content: Optional[str] = None
        self.module_info: Optional[ModuleInfo] = None
        self.classes: list[ClassInfo] = []
        self.functions: list[FunctionInfo] = []
        self.parameters: list[ParameterInfo] = []
        self.decorators: list[DecoratorInfo] = []
        self.imports: list[ImportInfo] = []
        self.inheritance: list[InheritanceEdge] = []
        self.calls: list[CallInfo] = []
        self.function_metrics: list[FunctionMetrics] = []

    def run(self) -> None:
        self.read_file_task.run()
        content = self.read_file_task.content
        assert content is not None
        self.raw_content = content
        self.parse()

    def parse(self) -> None:
        assert self.raw_content is not None
        filename = str(self.read_file_task.filename)
        module_tree = cst.parse_module(self.raw_content)
        wrapper = MetadataWrapper(module_tree)

        mod_name = infer_module_name(Path(filename), self.roots)
        collector = _ModuleCollector(
            module_name=mod_name, filename=filename, module=module_tree
        )
        wrapper.visit(collector)

        # Export results
        self.module_info = collector.module
        self.classes = collector.classes
        self.functions = collector.functions
        self.parameters = collector.parameters
        self.decorators = collector.decorators
        self.imports = collector.imports
        self.inheritance = collector.inheritance
        self.calls = collector.calls
        self.function_metrics = collector.function_metrics

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(filename={self.read_file_task.filename})"
