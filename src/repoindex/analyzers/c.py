"""C language analyzer backed by tree-sitter."""

from __future__ import annotations

from pathlib import Path

import tree_sitter_c
from tree_sitter import Language, Node, Parser

from repoindex.models import (
    AnalysisResult,
    CallSite,
    DeclarationArtifact,
    DeclarationKind,
    FunctionArtifact,
    ImportArtifact,
    ImportKind,
    ModuleArtifact,
)

_C_SUFFIXES = {".c", ".h"}
_LANGUAGE = Language(tree_sitter_c.language())


def _new_parser() -> Parser:
    """
    Create a parser configured for the C grammar.

    Parameters
    ----------
    None

    Returns
    -------
    tree_sitter.Parser
        Parser configured for ``tree-sitter-c``.
    """
    return Parser(_LANGUAGE)


def _module_name_for_path(path: Path, root: Path) -> str:
    """
    Derive the logical module name for one C source path.

    Parameters
    ----------
    path : pathlib.Path
        Source file being analyzed.
    root : pathlib.Path
        Repository root used for relative module naming.

    Returns
    -------
    str
        Dotted module identity derived from the relative file path.
    """
    relative = path.relative_to(root).with_suffix("")
    return ".".join(relative.parts)


def _node_text(node: Node, source: bytes) -> str:
    """
    Decode the source text owned by one syntax node.

    Parameters
    ----------
    node : tree_sitter.Node
        Syntax node whose text should be decoded.
    source : bytes
        Full source buffer.

    Returns
    -------
    str
        Decoded UTF-8 node text.
    """
    return source[node.start_byte : node.end_byte].decode("utf-8")


def _comment_to_summary(text: str) -> str | None:
    """
    Normalize one raw C comment block into summary text.

    Parameters
    ----------
    text : str
        Raw comment text including delimiters.

    Returns
    -------
    str | None
        Normalized summary text, or ``None`` when no content remains.
    """
    stripped = text.strip()
    if stripped.startswith("/*"):
        body = stripped.removeprefix("/*").removesuffix("*/")
        lines = [line.strip().lstrip("*").strip() for line in body.splitlines()]
    else:
        lines = [
            line.strip().removeprefix("//").strip() for line in stripped.splitlines()
        ]

    normalized_lines = [line for line in lines if line]
    if not normalized_lines:
        return None
    return "\n".join(normalized_lines)


def _leading_module_comment(root: Node, source: bytes) -> str | None:
    """
    Extract the first leading file comment as module summary text.

    Parameters
    ----------
    root : tree_sitter.Node
        Translation-unit root node.
    source : bytes
        Full source buffer.

    Returns
    -------
    str | None
        Normalized leading comment summary, or ``None`` when absent.
    """
    for child in root.children:
        if child.type == "comment":
            return _comment_to_summary(_node_text(child, source))
        if child.type != "preproc_include":
            return None
    return None


def _attached_comment_map(root: Node, source: bytes) -> dict[int, str]:
    """
    Map declaration start bytes to nearby leading comment summaries.

    Parameters
    ----------
    root : tree_sitter.Node
        Translation-unit root node.
    source : bytes
        Full source buffer.

    Returns
    -------
    dict[int, str]
        Attached comment summaries keyed by declaration start byte.
    """
    attached: dict[int, str] = {}
    pending_comment: str | None = None
    pending_end_row: int | None = None

    for child in root.children:
        if child.type == "comment":
            pending_comment = _comment_to_summary(_node_text(child, source))
            pending_end_row = child.end_point.row
            continue

        if pending_comment is not None and pending_end_row is not None:
            if child.start_point.row - pending_end_row <= 2:
                attached[child.start_byte] = pending_comment
            pending_comment = None
            pending_end_row = None

    return attached


def _named_descendants(node: Node) -> list[Node]:
    """
    Collect named descendants of one syntax node in source order.

    Parameters
    ----------
    node : tree_sitter.Node
        Parent syntax node.

    Returns
    -------
    list[tree_sitter.Node]
        Named descendant nodes in deterministic source order.
    """
    descendants: list[Node] = []
    stack = list(reversed(node.named_children))

    while stack:
        current = stack.pop()
        descendants.append(current)
        stack.extend(reversed(current.named_children))

    return descendants


def _unwrap_declarator_name(node: Node, source: bytes) -> str | None:
    """
    Resolve the identifier owned by one declarator node.

    Parameters
    ----------
    node : tree_sitter.Node
        Declarator node that may nest pointers or arrays.
    source : bytes
        Full source buffer.

    Returns
    -------
    str | None
        Identifier text when resolvable.
    """
    if node.type in {"identifier", "field_identifier"}:
        return _node_text(node, source)

    child = node.child_by_field_name("declarator")
    if child is not None:
        return _unwrap_declarator_name(child, source)

    for named_child in node.named_children:
        name = _unwrap_declarator_name(named_child, source)
        if name is not None:
            return name
    return None


def _extract_parameter_names(
    parameter_list: Node | None,
    source: bytes,
) -> tuple[str, ...]:
    """
    Extract deterministic parameter names from one parameter list.

    Parameters
    ----------
    parameter_list : tree_sitter.Node | None
        Parameter list node from a function declarator.
    source : bytes
        Full source buffer.

    Returns
    -------
    tuple[str, ...]
        Parameter names in declaration order.
    """
    if parameter_list is None:
        return ()

    parameters: list[str] = []
    for child in parameter_list.named_children:
        if child.type != "parameter_declaration":
            continue
        declarator = child.child_by_field_name("declarator")
        if declarator is None:
            continue
        name = _unwrap_declarator_name(declarator, source)
        if name is not None:
            parameters.append(name)
    return tuple(parameters)


def _call_site_from_expression(node: Node, source: bytes) -> CallSite | None:
    """
    Convert one tree-sitter call expression into a normalized call record.

    Parameters
    ----------
    node : tree_sitter.Node
        Call-expression node.
    source : bytes
        Full source buffer.

    Returns
    -------
    repoindex.models.CallSite | None
        Normalized call record, or ``None`` when no supported target exists.
    """
    function_node = node.child_by_field_name("function")
    if function_node is None:
        return None

    if function_node.type == "identifier":
        return CallSite(
            kind="name",
            target=_node_text(function_node, source),
            lineno=function_node.start_point.row + 1,
            col_offset=function_node.start_point.column,
        )

    if function_node.type == "field_expression":
        receiver = function_node.child_by_field_name("argument")
        field = function_node.child_by_field_name("field")
        if receiver is None or field is None:
            return None
        return CallSite(
            kind="attribute",
            target=_node_text(field, source),
            lineno=field.start_point.row + 1,
            col_offset=field.start_point.column,
            base=_node_text(receiver, source),
        )

    return CallSite(
        kind="unresolved",
        target="",
        lineno=function_node.start_point.row + 1,
        col_offset=function_node.start_point.column,
    )


def _extract_calls(body: Node | None, source: bytes) -> tuple[CallSite, ...]:
    """
    Extract normalized calls from one function body.

    Parameters
    ----------
    body : tree_sitter.Node | None
        Compound-statement node owning the function body.
    source : bytes
        Full source buffer.

    Returns
    -------
    tuple[repoindex.models.CallSite, ...]
        Call records in deterministic source order.
    """
    if body is None:
        return ()

    calls: list[CallSite] = []
    for node in _named_descendants(body):
        if node.type != "call_expression":
            continue
        call = _call_site_from_expression(node, source)
        if call is not None:
            calls.append(call)
    return tuple(calls)


def _returns_value(body: Node | None) -> int:
    """
    Detect whether one function body contains a value-returning statement.

    Parameters
    ----------
    body : tree_sitter.Node | None
        Compound-statement node owning the function body.

    Returns
    -------
    int
        ``1`` when the body contains ``return <expr>;``, else ``0``.
    """
    if body is None:
        return 0

    for node in _named_descendants(body):
        if node.type == "return_statement" and len(node.named_children) > 0:
            return 1
    return 0


def _extract_functions(root: Node, source: bytes) -> tuple[FunctionArtifact, ...]:
    """
    Extract top-level C function definitions from one translation unit.

    Parameters
    ----------
    root : tree_sitter.Node
        Translation-unit root node.
    source : bytes
        Full source buffer.

    Returns
    -------
    tuple[repoindex.models.FunctionArtifact, ...]
        Deterministic function artifacts ordered by source position.
    """
    functions: list[FunctionArtifact] = []

    for child in root.children:
        if child.type != "function_definition":
            continue

        declarator = child.child_by_field_name("declarator")
        body = child.child_by_field_name("body")
        if declarator is None:
            continue

        name = _unwrap_declarator_name(declarator, source)
        if name is None:
            continue

        parameter_list = declarator.child_by_field_name("parameters")
        parameters = _extract_parameter_names(parameter_list, source)
        signature_end = body.start_byte if body is not None else declarator.end_byte
        signature = source[child.start_byte : signature_end].decode("utf-8").strip()
        is_public = int(
            not any(
                sub.type == "storage_class_specifier"
                and _node_text(sub, source) == "static"
                for sub in child.children
            )
        )

        functions.append(
            FunctionArtifact(
                name=name,
                lineno=child.start_point.row + 1,
                end_lineno=body.end_point.row + 1 if body is not None else None,
                signature=" ".join(signature.split()),
                docstring=None,
                has_docstring=0,
                is_method=0,
                is_public=is_public,
                parameters=parameters,
                returns_value=_returns_value(body),
                yields_value=0,
                raises=0,
                has_asserts=0,
                decorators=(),
                calls=_extract_calls(body, source),
                callable_refs=(),
            )
        )

    return tuple(functions)


def _declaration_name(node: Node, source: bytes) -> str | None:
    """
    Resolve the exposed declaration name for one top-level type node.

    Parameters
    ----------
    node : tree_sitter.Node
        Declaration node being normalized.
    source : bytes
        Full source buffer.

    Returns
    -------
    str | None
        Declaration name when one is present.
    """
    if node.type == "type_definition":
        named_children = list(node.named_children)
        if not named_children:
            return None
        alias_node = named_children[-1]
        if alias_node.type in {"type_identifier", "identifier", "primitive_type"}:
            return _node_text(alias_node, source)
        return None

    for named_child in node.named_children:
        if named_child.type in {"type_identifier", "identifier"}:
            return _node_text(named_child, source)
    return None


def _append_declaration(
    declarations: list[DeclarationArtifact],
    node: Node,
    source: bytes,
    *,
    attached_comments: dict[int, str],
    inherited_comment: str | None = None,
    kind: DeclarationKind,
) -> None:
    """
    Append one normalized declaration artifact when the node is named.

    Parameters
    ----------
    declarations : list[repoindex.models.DeclarationArtifact]
        Accumulator updated in source order.
    node : tree_sitter.Node
        Declaration node being normalized.
    source : bytes
        Full source buffer.
    attached_comments : dict[int, str]
        Leading comment summaries keyed by declaration start byte.
    inherited_comment : str | None, optional
        Leading comment summary inherited from an owning declaration node.
    kind : str
        Stable declaration classifier.

    Returns
    -------
    None
        The declaration is appended only when a usable name is present.
    """
    name = _declaration_name(node, source)
    if name is None:
        return

    declarations.append(
        DeclarationArtifact(
            name=name,
            kind=kind,
            lineno=node.start_point.row + 1,
            signature=" ".join(_node_text(node, source).split()),
            docstring=attached_comments.get(node.start_byte, inherited_comment),
        )
    )


def _extract_declarations(root: Node, source: bytes) -> tuple[DeclarationArtifact, ...]:
    """
    Extract top-level C declarations useful for exact and semantic lookup.

    Parameters
    ----------
    root : tree_sitter.Node
        Translation-unit root node.
    source : bytes
        Full source buffer.

    Returns
    -------
    tuple[repoindex.models.DeclarationArtifact, ...]
        Deterministic declaration artifacts ordered by source position.
    """
    declarations: list[DeclarationArtifact] = []
    attached_comments = _attached_comment_map(root, source)

    for child in root.children:
        if child.type == "struct_specifier":
            _append_declaration(
                declarations,
                child,
                source,
                attached_comments=attached_comments,
                kind="struct",
            )
            continue

        if child.type == "enum_specifier":
            _append_declaration(
                declarations,
                child,
                source,
                attached_comments=attached_comments,
                kind="enum",
            )
            continue

        if child.type != "type_definition":
            continue

        child_comment = attached_comments.get(child.start_byte)
        for named_child in child.named_children:
            if named_child.type == "struct_specifier":
                _append_declaration(
                    declarations,
                    named_child,
                    source,
                    attached_comments=attached_comments,
                    inherited_comment=child_comment,
                    kind="struct",
                )
            elif named_child.type == "enum_specifier":
                _append_declaration(
                    declarations,
                    named_child,
                    source,
                    attached_comments=attached_comments,
                    inherited_comment=child_comment,
                    kind="enum",
                )

        _append_declaration(
            declarations,
            child,
            source,
            attached_comments=attached_comments,
            kind="typedef",
        )

    return tuple(declarations)


def _extract_imports(root: Node, source: bytes) -> tuple[ImportArtifact, ...]:
    """
    Extract include rows from one translation unit.

    Parameters
    ----------
    root : tree_sitter.Node
        Translation-unit root node.
    source : bytes
        Full source buffer.

    Returns
    -------
    tuple[repoindex.models.ImportArtifact, ...]
        Deterministic include rows ordered by source position.
    """
    imports: list[ImportArtifact] = []

    for child in root.children:
        if child.type != "preproc_include":
            continue
        include_target = None
        include_kind: ImportKind = "include_local"
        for named_child in child.named_children:
            if named_child.type == "string_literal":
                include_target = _node_text(named_child, source).strip('"')
                include_kind = "include_local"
                break
            if named_child.type == "system_lib_string":
                include_target = _node_text(named_child, source).strip("<>")
                include_kind = "include_system"
                break
        if include_target is None:
            continue
        imports.append(
            ImportArtifact(
                name=include_target,
                alias=None,
                lineno=child.start_point.row + 1,
                kind=include_kind,
            )
        )

    return tuple(imports)


class CAnalyzer:
    """
    Concrete C analyzer for repository indexing.

    Parameters
    ----------
    None

    Notes
    -----
    This analyzer is backed by ``tree-sitter-c`` so further C extraction work
    can evolve from a real parse tree instead of regex heuristics.
    """

    name = "c"
    version = "2"
    discovery_globs: tuple[str, ...] = ("*.c", "*.h")

    def supports_path(self, path: Path) -> bool:
        """
        Decide whether the analyzer accepts a C-family source path.

        Parameters
        ----------
        path : pathlib.Path
            Candidate repository file.

        Returns
        -------
        bool
            ``True`` when the file is a ``.c`` or ``.h`` source file.
        """
        return path.suffix in _C_SUFFIXES

    def analyze_file(self, path: Path, root: Path) -> AnalysisResult:
        """
        Analyze one C-family source file into normalized artifacts.

        Parameters
        ----------
        path : pathlib.Path
            C-family source file to analyze.
        root : pathlib.Path
            Repository root used for module-name derivation.

        Returns
        -------
        repoindex.models.AnalysisResult
            Normalized analysis result for the file.
        """
        source = path.read_bytes()
        root_node = _new_parser().parse(source).root_node
        module_comment = _leading_module_comment(root_node, source)
        return AnalysisResult(
            source_path=path,
            module=ModuleArtifact(
                name=_module_name_for_path(path, root),
                docstring=module_comment,
                has_docstring=int(module_comment is not None),
            ),
            classes=(),
            functions=_extract_functions(root_node, source),
            declarations=_extract_declarations(root_node, source),
            imports=_extract_imports(root_node, source),
        )
