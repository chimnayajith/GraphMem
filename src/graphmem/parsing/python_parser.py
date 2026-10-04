from __future__ import annotations

"""Tree-sitter based Python repository parser for GraphMem.

This parser intentionally keeps the same GraphMem output model as the
previous Python ``ast`` parser, but uses Tree-sitter for parsing.

The important design choice is that the parser is language-adapter code:
GraphMem receives only CodeEntity / Relation objects.  This makes it possible
to add Java, JavaScript, C/C++, etc. later without changing the graph layer.

Current Python support:
    - repository / directory / file entities
    - classes / functions / methods
    - statement-level entities
    - CONTAINS
    - IMPORTS
    - CALLS, including ClassA().method1()
    - statement DEF/USE metadata
    - intra-procedural DATAFLOW_DEF_USE

Tree-sitter also gives us a useful property that Python's ``ast.parse`` does
not: a syntactically incomplete file can still produce a tree containing
ERROR nodes.  We therefore record parse errors instead of simply throwing
away the whole file.
"""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

from tree_sitter import Language, Parser
import tree_sitter_python as tree_sitter_python

from graphmem.models.entities import CodeEntity, EntityType
from graphmem.models.relations import Relation, RelationType
from graphmem.models.repository import ParsedRepository
from graphmem.parsing.base import LanguageParser


DEFAULT_EXCLUDED_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env", ".tox",
    ".mypy_cache", ".pytest_cache", "build", "dist", "node_modules",
    ".idea", ".vscode",
}


# Python Tree-sitter node types that represent statements.  Compound
# statements are included too; their nested statements are represented as
# their own nodes, which gives us a useful fine-grained graph.
STATEMENT_TYPES = {
    "assert_statement",
    "break_statement",
    "continue_statement",
    "delete_statement",
    "exec_statement",
    "expression_statement",
    "for_statement",
    "global_statement",
    "if_statement",
    "import_from_statement",
    "import_statement",
    "nonlocal_statement",
    "pass_statement",
    "raise_statement",
    "return_statement",
    "try_statement",
    "while_statement",
    "with_statement",
    "match_statement",
}

DEFINITION_TYPES = {
    "class_definition",
    "function_definition",
    "async_function_definition",
}


@dataclass
class _FileRecord:
    relative_path: str
    absolute_path: Path
    module_name: str
    entity_id: str


@dataclass
class _ParsedFile:
    record: _FileRecord
    tree: object
    source: bytes


@dataclass
class _Scope:
    entity: CodeEntity
    qualified_parts: list[str]
    kind: str  # file / class / function / method


class PythonParser(LanguageParser):
    """Parse Python repositories with Tree-sitter into GraphMem's schema."""

    language = "python"

    def __init__(self, excluded_dirs: Optional[set[str]] = None) -> None:
        self.excluded_dirs = (
            set(excluded_dirs)
            if excluded_dirs is not None
            else set(DEFAULT_EXCLUDED_DIRS)
        )

        # Tree-sitter grammar.  Keep this parser object reusable.
        self._language = Language(tree_sitter_python.language())
        self._parser = self._new_parser()

        self._parsed_files: list[_ParsedFile] = []
        self._entities_by_qualified_name: dict[str, CodeEntity] = {}
        self._entities_by_file_and_name: dict[tuple[str, str], CodeEntity] = {}
        self._entities_by_module_and_name: dict[tuple[str, str], CodeEntity] = {}

        # Import aliases per file, e.g.:
        #   from pkg.foo import bar as baz  -> baz: pkg.foo.bar
        self._imports_by_file: dict[str, dict[str, str]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_repository(self, repository_path: str) -> ParsedRepository:
        repo_root = Path(repository_path).resolve()
        if not repo_root.is_dir():
            raise NotADirectoryError(str(repo_root))

        repo_name = self.resolve_repo_name(str(repo_root))
        version = self.resolve_version(str(repo_root))
        parsed = ParsedRepository(repository_path=str(repo_root))

        repo_entity_id = f"repo://{repo_name}@{version}"
        parsed.add_entity(CodeEntity(
            id=repo_entity_id,
            type=EntityType.REPOSITORY,
            name=repo_name,
            metadata={"language": self.language, "version": version},
        ))

        file_records = self._discover_files(repo_root, repo_name, version)
        module_map = {r.module_name: r for r in file_records}

        self._build_directory_hierarchy(
            parsed=parsed,
            repo_name=repo_name,
            repo_entity_id=repo_entity_id,
            version=version,
            file_records=file_records,
        )

        for record in file_records:
            parsed.add_entity(CodeEntity(
                id=record.entity_id,
                type=EntityType.FILE,
                name=PurePosixPath(record.relative_path).name,
                path=record.relative_path,
                qualified_name=record.module_name,
                metadata={
                    "language": self.language,
                    "version": version,
                    "parser": "tree-sitter",
                    "imports": [],
                },
            ))

        self._parsed_files = []
        self._imports_by_file = {}

        # Pass 1: parse + entities + statements + imports.
        for record in file_records:
            self._parse_file(
                record=record,
                repo_name=repo_name,
                version=version,
                module_map=module_map,
                parsed=parsed,
            )

        # Pass 2: build symbol indexes once all entities exist.
        self._build_symbol_indexes(parsed)

        # Pass 3: calls.
        self._resolve_calls(parsed)

        # Pass 4: DEF/USE + data-flow.
        self._build_dataflow(parsed)

        return parsed

    # ------------------------------------------------------------------
    # Tree-sitter parser compatibility
    # ------------------------------------------------------------------

    def _new_parser(self) -> Parser:
        parser = Parser()
        # tree-sitter >= 0.22 supports Parser(language) while some versions
        # expose Parser() + parser.language.  Supporting both keeps the
        # adapter easier to install across environments.
        try:
            parser.language = self._language
        except Exception:
            try:
                parser.set_language(self._language)
            except AttributeError:
                parser = Parser(self._language)
        return parser

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------

    def _discover_files(self, repo_root: Path, repo_name: str, version: str):
        records: list[_FileRecord] = []
        for path in sorted(repo_root.rglob("*.py")):
            relative = path.relative_to(repo_root)
            if any(part in self.excluded_dirs for part in relative.parts):
                continue
            relative_path = relative.as_posix()
            module_name = self._module_name_for(relative_path)
            entity_id = self.make_entity_id(
                repo_name, relative_path, version
            )
            records.append(_FileRecord(
                relative_path=relative_path,
                absolute_path=path,
                module_name=module_name,
                entity_id=entity_id,
            ))
        return records

    @staticmethod
    def _module_name_for(relative_path: str) -> str:
        parts = relative_path.split("/")
        filename = parts[-1]
        if filename.endswith(".py"):
            filename = filename[:-3]
        parts[-1] = filename
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(p for p in parts if p)

    # ------------------------------------------------------------------
    # Directory hierarchy
    # ------------------------------------------------------------------

    def _build_directory_hierarchy(
        self,
        *,
        parsed: ParsedRepository,
        repo_name: str,
        repo_entity_id: str,
        version: str,
        file_records: list[_FileRecord],
    ) -> None:
        directory_paths: set[str] = set()
        for record in file_records:
            parent = PurePosixPath(record.relative_path).parent.as_posix()
            while parent not in (".", ""):
                directory_paths.add(parent)
                parent = PurePosixPath(parent).parent.as_posix()

        directory_entity_ids = {"": repo_entity_id}

        for directory_path in sorted(
            directory_paths, key=lambda x: (x.count("/"), x)
        ):
            entity_id = self.make_entity_id(
                repo_name, directory_path, version
            )
            directory_entity_ids[directory_path] = entity_id
            parsed.add_entity(CodeEntity(
                id=entity_id,
                type=EntityType.DIRECTORY,
                name=PurePosixPath(directory_path).name,
                path=directory_path,
                metadata={"language": self.language, "version": version},
            ))

            parent = PurePosixPath(directory_path).parent.as_posix()
            if parent == ".":
                parent = ""
            parsed.add_relation(Relation(
                source_id=directory_entity_ids[parent],
                target_id=entity_id,
                type=RelationType.CONTAINS,
            ))

        for record in file_records:
            parent = PurePosixPath(record.relative_path).parent.as_posix()
            if parent == ".":
                parent = ""
            parsed.add_relation(Relation(
                source_id=directory_entity_ids.get(parent, repo_entity_id),
                target_id=record.entity_id,
                type=RelationType.CONTAINS,
            ))

    # ------------------------------------------------------------------
    # Per-file parsing
    # ------------------------------------------------------------------

    def _parse_file(
        self,
        *,
        record: _FileRecord,
        repo_name: str,
        version: str,
        module_map: dict[str, _FileRecord],
        parsed: ParsedRepository,
    ) -> None:
        file_entity = parsed.get_entity(record.entity_id)
        if file_entity is None:
            return

        try:
            source = record.absolute_path.read_bytes()
        except OSError as exc:
            file_entity.metadata["read_error"] = str(exc)
            return

        try:
            tree = self._parser.parse(source)
        except Exception as exc:
            file_entity.metadata["parse_error"] = str(exc)
            return

        self._parsed_files.append(_ParsedFile(record, tree, source))

        error_nodes = self._find_error_nodes(tree.root_node)
        if error_nodes:
            file_entity.metadata["parse_errors"] = [
                {
                    "type": n.type,
                    "start_line": n.start_point[0] + 1,
                    "end_line": n.end_point[0] + 1,
                    "text": self._node_text(n, source)[:200],
                }
                for n in error_nodes[:50]
            ]

        # Create all definitions and statements.
        self._extract_scope(
            root=tree.root_node,
            file_entity=file_entity,
            record=record,
            repo_name=repo_name,
            version=version,
            source=source,
            parsed=parsed,
        )

        self._extract_imports(
            tree=tree.root_node,
            record=record,
            module_map=module_map,
            file_entity=file_entity,
            parsed=parsed,
            source=source,
        )

    # ------------------------------------------------------------------
    # Entity + statement extraction
    # ------------------------------------------------------------------

    def _extract_scope(
        self,
        *,
        root,
        file_entity: CodeEntity,
        record: _FileRecord,
        repo_name: str,
        version: str,
        source: bytes,
        parsed: ParsedRepository,
    ) -> None:
        statement_counter = [0]

        def process_nodes(nodes, scope: _Scope) -> None:
            for node in nodes:
                # Decorated definitions are wrappers in Tree-sitter.  The
                # actual class/function is in the definition child.
                if node.type == "decorated_definition":
                    definition = self._first_child_of_types(
                        node, DEFINITION_TYPES
                    )
                    if definition is not None:
                        process_definition(definition, scope)
                    continue

                if node.type in DEFINITION_TYPES:
                    process_definition(node, scope)
                    continue

                if self._is_statement_node(node):
                    statement_counter[0] += 1
                    statement = self._add_statement(
                        node=node,
                        scope=scope,
                        record=record,
                        repo_name=repo_name,
                        version=version,
                        source=source,
                        number=statement_counter[0],
                        parsed=parsed,
                    )

                    # Compound statements contain nested statements.  Do
                    # not descend into expressions here, only actual nested
                    # statement-bearing children.
                    for child in self._nested_statement_children(node):
                        process_nodes([child], scope)
                    continue

                # Module/class/function bodies are handled explicitly. For
                # wrappers such as suite, just descend to find statements.
                for child in node.named_children:
                    if child.type in DEFINITION_TYPES or self._is_statement_node(child):
                        process_nodes([child], scope)

        def process_definition(node, parent_scope: _Scope) -> None:
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            name = self._node_text(name_node, source)
            is_class = node.type == "class_definition"
            entity_type = EntityType.CLASS if is_class else (
                EntityType.METHOD
                if parent_scope.kind == "class"
                else EntityType.FUNCTION
            )

            qualified_parts = parent_scope.qualified_parts + [name]
            qualified_name = ".".join(qualified_parts)
            entity_id = self.make_entity_id(
                repo_name,
                record.relative_path,
                version,
                qualified_name=qualified_name,
            )

            metadata = {
                "language": self.language,
                "version": version,
                "parser": "tree-sitter",
                "decorators": [],
            }
            if is_class:
                bases = node.child_by_field_name("superclasses")
                if bases is not None:
                    metadata["bases"] = [
                        self._node_text(c, source)
                        for c in bases.named_children
                    ]

            entity = CodeEntity(
                id=entity_id,
                type=entity_type,
                name=name,
                path=record.relative_path,
                qualified_name=qualified_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                parent_id=parent_scope.entity.id,
                metadata=metadata,
            )
            parsed.add_entity(entity)
            parsed.add_relation(Relation(
                source_id=parent_scope.entity.id,
                target_id=entity_id,
                type=RelationType.CONTAINS,
            ))

            child_scope = _Scope(
                entity=entity,
                qualified_parts=qualified_parts,
                kind="class" if is_class else "function",
            )

            body = node.child_by_field_name("body")
            if body is not None:
                process_nodes(body.named_children, child_scope)

        root_scope = _Scope(
            entity=file_entity,
            qualified_parts=[],
            kind="file",
        )
        process_nodes(root.named_children, root_scope)

    @staticmethod
    def _is_statement_node(node) -> bool:
        return node.type in STATEMENT_TYPES

    @staticmethod
    def _nested_statement_children(node):
        """Return direct/nested statement nodes without entering definitions."""
        result = []

        def collect(n):
            for child in n.named_children:
                if child.type in DEFINITION_TYPES or child.type == "decorated_definition":
                    continue
                if child.type in STATEMENT_TYPES:
                    result.append(child)
                elif child.type in {
                    "block", "else_clause", "elif_clause", "finally_clause",
                    "except_clause", "case_clause", "conditional_expression",
                }:
                    collect(child)
                elif child.type.endswith("_clause"):
                    collect(child)

        # For a compound statement, its body/clauses contain statements.
        collect(node)
        # The node itself may appear through unusual grammar nesting; avoid it.
        return [n for n in result if n.id != node.id]

    def _add_statement(
        self,
        *,
        node,
        scope: _Scope,
        record: _FileRecord,
        repo_name: str,
        version: str,
        source: bytes,
        number: int,
        parsed: ParsedRepository,
    ) -> CodeEntity:
        source_text = self._node_text(node, source)
        qualified_scope = ".".join(scope.qualified_parts) or record.module_name
        qualified_name = f"{qualified_scope}::statement_{number}"
        entity_id = self.make_entity_id(
            repo_name,
            record.relative_path,
            version,
            qualified_name=qualified_name,
        )
        entity = CodeEntity(
            id=entity_id,
            type=EntityType.STATEMENT,
            name=self._statement_name(source_text, number),
            path=record.relative_path,
            qualified_name=qualified_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            parent_id=scope.entity.id,
            metadata={
                "language": self.language,
                "version": version,
                "parser": "tree-sitter",
                "ast_type": node.type,
                "source": source_text,
                "statement_index": number,
                "tree_sitter_start_byte": node.start_byte,
                "tree_sitter_end_byte": node.end_byte,
                "uses": [],
                "defines": [],
            },
        )
        parsed.add_entity(entity)
        parsed.add_relation(Relation(
            source_id=scope.entity.id,
            target_id=entity_id,
            type=RelationType.CONTAINS,
        ))
        return entity

    @staticmethod
    def _statement_name(text: str, number: int) -> str:
        text = " ".join(text.strip().split())
        if len(text) > 80:
            return text[:77] + "..."
        return text or f"statement_{number}"

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def _extract_imports(
        self,
        *,
        tree,
        record: _FileRecord,
        module_map: dict[str, _FileRecord],
        file_entity: CodeEntity,
        parsed: ParsedRepository,
        source: bytes,
    ) -> None:
        aliases: dict[str, str] = {}

        current_package = (
            record.module_name.rsplit(".", 1)[0]
            if "." in record.module_name
            else ""
        )

        if record.absolute_path.name == "__init__.py":
            current_package = record.module_name

        for node in self._walk_named(tree):
            # --------------------------------------------------------------
            # import os
            # import pkg.sub.helpers
            # --------------------------------------------------------------
            if node.type == "import_statement":
                raw = self._node_text(node, source)
                file_entity.metadata.setdefault("imports", []).append(raw)

                for imported in self._import_statement_names(node, source):
                    module = imported["module"]
                    local = imported["local"]

                    aliases[local] = module

                    target = module_map.get(module)

                    if target is not None and target.entity_id != record.entity_id:
                        parsed.add_relation(Relation(
                            source_id=record.entity_id,
                            target_id=target.entity_id,
                            type=RelationType.IMPORTS,
                            metadata={
                                "resolved_via": "module_path_match",
                                "imported": module,
                            },
                        ))

            # --------------------------------------------------------------
            # from .base import Base
            # from pkg.sub.helpers import normalize
            # --------------------------------------------------------------
            elif node.type == "import_from_statement":
                raw = self._node_text(node, source)
                file_entity.metadata.setdefault("imports", []).append(raw)

                module = ""
                level = 0

                # Find the relative_import / module portion
                for child in node.named_children:

                    if child.type == "relative_import":
                        text = self._node_text(child, source)

                        # Count leading dots
                        level = len(text) - len(text.lstrip("."))

                        module = text[level:]

                        break

                    elif child.type == "dotted_name":
                        # Absolute import:
                        #
                        # from pkg.sub.helpers import normalize
                        #
                        module = self._node_text(child, source)
                        break

                base_module = self._resolve_relative_module(
                    current_package,
                    module,
                    level,
                )

                # ----------------------------------------------------------
                # Resolve the imported module to a repository file.
                #
                # from .base import Base
                #
                # base_module = pkg.sub.base
                # ----------------------------------------------------------
                target = module_map.get(base_module)

                if target is not None and target.entity_id != record.entity_id:
                    parsed.add_relation(Relation(
                        source_id=record.entity_id,
                        target_id=target.entity_id,
                        type=RelationType.IMPORTS,
                        metadata={
                            "resolved_via": "module_path_match",
                            "imported": base_module,
                            "relative_level": level,
                        },
                    ))

                # ----------------------------------------------------------
                # Record imported symbols as aliases.
                # ----------------------------------------------------------
                imported_names = self._extract_from_import_names(
                    node,
                    source,
                )

                for name, local in imported_names:
                    qualified = (
                        f"{base_module}.{name}"
                        if base_module
                        else name
                    )

                    aliases[local] = qualified

        self._imports_by_file[record.relative_path] = aliases

    @staticmethod
    def _extract_from_import_names(node, source: bytes):
        result = []

        for child in node.named_children:

            if child.type == "aliased_import":
                name_node = child.child_by_field_name("name")
                alias_node = child.child_by_field_name("alias")

                if name_node is None:
                    continue

                name = PythonParser._node_text(name_node, source)

                local = (
                    PythonParser._node_text(alias_node, source)
                    if alias_node is not None
                    else name
                )

                result.append((name, local))

            elif child.type == "dotted_name":
                name = PythonParser._node_text(child, source)

                result.append((
                    name,
                    name.split(".")[-1],
                ))

            elif child.type == "wildcard_import":
                result.append(("*", "*"))

        return result

    @staticmethod
    def _resolve_relative_module(current_package: str, module: str, level: int) -> str:
        if level == 0:
            return module
        parts = current_package.split(".") if current_package else []
        strip = level - 1
        if strip <= len(parts):
            parts = parts[:len(parts) - strip]
        else:
            parts = []
        base = ".".join(parts)
        return f"{base}.{module}" if base and module else (base or module)

    @staticmethod
    def _import_statement_names(node, source: bytes):
        result = []
        for child in node.named_children:
            if child.type in {"dotted_name", "aliased_import"}:
                if child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")
                    module = PythonParser._node_text(name_node, source)
                    local = PythonParser._node_text(alias_node, source) if alias_node else module.split(".")[0]
                else:
                    module = PythonParser._node_text(child, source)
                    local = module.split(".")[0]
                result.append({"module": module, "local": local})
        return result

    # ------------------------------------------------------------------
    # Symbol indexes
    # ------------------------------------------------------------------

    def _build_symbol_indexes(self, parsed: ParsedRepository) -> None:
        self._entities_by_qualified_name.clear()
        self._entities_by_file_and_name.clear()
        self._entities_by_module_and_name.clear()

        for entity in parsed.entities:
            if entity.type not in {
                EntityType.CLASS,
                EntityType.FUNCTION,
                EntityType.METHOD,
            }:
                continue
            if entity.qualified_name:
                self._entities_by_qualified_name[entity.qualified_name] = entity
            if entity.path:
                key = (entity.path, entity.name)
                # Prefer the first top-level matching symbol for simple calls.
                self._entities_by_file_and_name.setdefault(key, entity)

                file_entity = next((
                    candidate for candidate in parsed.entities
                    if candidate.type == EntityType.FILE
                    and candidate.path == entity.path
                ), None)
                if file_entity and file_entity.qualified_name:
                    self._entities_by_module_and_name[
                        (file_entity.qualified_name, entity.name)
                    ] = entity

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    def _resolve_calls(self, parsed: ParsedRepository) -> None:
        for parsed_file in self._parsed_files:
            resolver = _TreeSitterCallResolver(
                parser=self,
                parsed=parsed,
                parsed_file=parsed_file,
            )
            resolver.run()
            for relation in resolver.relations:
                if not self._has_relation(parsed, relation):
                    parsed.add_relation(relation)

    def _has_relation(self, parsed: ParsedRepository, relation: Relation) -> bool:
        return any(
            r.source_id == relation.source_id
            and r.target_id == relation.target_id
            and r.type == relation.type
            for r in parsed.relations
        )

    # ------------------------------------------------------------------
    # Data flow
    # ------------------------------------------------------------------

    def _build_dataflow(self, parsed: ParsedRepository) -> None:
        for parsed_file in self._parsed_files:
            analyzer = _TreeSitterDataFlowAnalyzer(
                parser=self,
                parsed=parsed,
                parsed_file=parsed_file,
            )
            analyzer.run()
            for relation in analyzer.relations:
                if not self._has_relation(parsed, relation):
                    parsed.add_relation(relation)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _node_text(node, source: bytes) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    @staticmethod
    def _walk_named(node):
        yield node
        for child in node.named_children:
            yield from PythonParser._walk_named(child)

    @staticmethod
    def _find_error_nodes(node):
        result = []
        for current in PythonParser._walk_named(node):
            if current.type == "ERROR" or current.is_missing:
                result.append(current)
        return result

    @staticmethod
    def _first_child_of_types(node, types: set[str]):
        for child in node.named_children:
            if child.type in types:
                return child
        return None


# ======================================================================
# Tree-sitter CALL resolver
# ======================================================================


class _TreeSitterCallResolver:
    def __init__(self, *, parser: PythonParser, parsed: ParsedRepository, parsed_file: _ParsedFile):
        self.parser = parser
        self.parsed = parsed
        self.parsed_file = parsed_file
        self.record = parsed_file.record
        self.source = parsed_file.source
        self.relations: list[Relation] = []
        self.current_callable: Optional[CodeEntity] = None
        self.current_class: Optional[CodeEntity] = None
        self.current_statement: Optional[CodeEntity] = None
        self.statement_by_span = {
            (e.start_line, e.end_line): e
            for e in parsed.entities
            if e.type == EntityType.STATEMENT
            and e.path == self.record.relative_path
        }

    def run(self) -> None:
        self._visit(self.parsed_file.tree.root_node)

    def _visit(self, node) -> None:
        old_callable = self.current_callable
        old_class = self.current_class
        old_statement = self.current_statement

        if node.type in {"class_definition"}:
            entity = self._definition_entity(node)
            self.current_class = entity or self.current_class
        elif node.type in {"function_definition", "async_function_definition"}:
            self.current_callable = self._definition_entity(node)
        elif node.type in STATEMENT_TYPES:
            self.current_statement = self._statement_entity(node)

        if node.type == "call":
            self._handle_call(node)

        for child in node.named_children:
            # Definitions create their own scope, but nested methods/classes
            # still need to be visited.
            self._visit(child)

        self.current_callable = old_callable
        self.current_class = old_class
        self.current_statement = old_statement

    def _handle_call(self, node) -> None:
        function_node = node.child_by_field_name("function")
        if function_node is None:
            # Some grammar versions expose the callee as the first named child.
            function_node = node.named_children[0] if node.named_children else None
        if function_node is None:
            return

        target = self._resolve_target(function_node)
        source = self.current_statement or self.current_callable
        if target is None or source is None:
            return

        self.relations.append(Relation(
            source_id=source.id,
            target_id=target.id,
            type=RelationType.CALLS,
            metadata={
                "call": self.parser._node_text(node, self.source),
                "resolved_via": self._resolution_method(function_node),
            },
        ))

    def _definition_entity(self, node) -> Optional[CodeEntity]:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None
        name = self.parser._node_text(name_node, self.source)

        # Exact line/name match is robust and avoids ambiguities from overloads.
        candidates = [
            e for e in self.parsed.entities
            if e.path == self.record.relative_path
            and e.name == name
            and e.type in {EntityType.CLASS, EntityType.FUNCTION, EntityType.METHOD}
            and e.start_line == node.start_point[0] + 1
        ]
        return candidates[0] if candidates else None

    def _statement_entity(self, node) -> Optional[CodeEntity]:
        key = (node.start_point[0] + 1, node.end_point[0] + 1)
        return self.statement_by_span.get(key)

    def _resolve_target(self, function_node) -> Optional[CodeEntity]:
        if function_node.type == "identifier":
            return self._resolve_name(self.parser._node_text(function_node, self.source))

        if function_node.type == "attribute":
            attr = function_node.child_by_field_name("attribute")
            object_node = function_node.child_by_field_name("object")
            if attr is None or object_node is None:
                return None
            method = self.parser._node_text(attr, self.source)

            # self.foo()
            if object_node.type == "identifier":
                receiver = self.parser._node_text(object_node, self.source)
                if receiver == "self" and self.current_class:
                    return self.parser._entities_by_qualified_name.get(
                        f"{self.current_class.qualified_name}.{method}"
                    )

                # ClassA.foo()
                class_entity = self._resolve_name(receiver)
                if class_entity and class_entity.type == EntityType.CLASS:
                    return self.parser._entities_by_qualified_name.get(
                        f"{class_entity.qualified_name}.{method}"
                    )

                # obj.foo()
                inferred = self._infer_variable_class(receiver)
                if inferred:
                    return self.parser._entities_by_qualified_name.get(
                        f"{inferred.qualified_name}.{method}"
                    )

            # ClassA().foo()
            if object_node.type == "call":
                constructor = object_node.child_by_field_name("function")
                if constructor is None and object_node.named_children:
                    constructor = object_node.named_children[0]
                if constructor and constructor.type == "identifier":
                    class_entity = self._resolve_name(
                        self.parser._node_text(constructor, self.source)
                    )
                    if class_entity and class_entity.type == EntityType.CLASS:
                        return self.parser._entities_by_qualified_name.get(
                            f"{class_entity.qualified_name}.{method}"
                        )

        return None

    def _resolve_name(self, name: str) -> Optional[CodeEntity]:
        entity = self.parser._entities_by_file_and_name.get(
            (self.record.relative_path, name)
        )
        if entity:
            return entity

        imported = self.parser._imports_by_file.get(self.record.relative_path, {}).get(name)
        if imported:
            # Exact imported symbol.
            target = self.parser._entities_by_qualified_name.get(imported)
            if target:
                return target
            # Imported module/class name.
            module_name, _, symbol = imported.rpartition(".")
            if symbol:
                target = self.parser._entities_by_module_and_name.get((module_name, symbol))
                if target:
                    return target

        if self.current_class:
            target = self.parser._entities_by_qualified_name.get(
                f"{self.current_class.qualified_name}.{name}"
            )
            if target:
                return target

        matches = [
            entity for (module, symbol), entity
            in self.parser._entities_by_module_and_name.items()
            if symbol == name
        ]
        return matches[0] if len(matches) == 1 else None

    def _infer_variable_class(self, variable: str) -> Optional[CodeEntity]:
        # Search assignment statements before this call.
        call_line = self.current_statement.start_line if self.current_statement else 10**9
        candidates = [
            e for e in self.parsed.entities
            if e.type == EntityType.STATEMENT
            and e.path == self.record.relative_path
            and e.end_line is not None
            and e.end_line <= call_line
        ]
        for entity in sorted(candidates, key=lambda e: e.end_line or 0, reverse=True):
            text = entity.metadata.get("source", "")
            if not text.startswith(" "):
                # Keep source handling simple; Tree-sitter parsing below is
                # sufficient even when the original statement is multiline.
                pass
            # Parse only the statement with the same Tree-sitter parser.
            try:
                tree = self.parser._parser.parse(text.encode())
            except Exception:
                continue
            root = tree.root_node
            for node in PythonParser._walk_named(root):
                if node.type != "assignment":
                    continue
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                if left is None or right is None or left.type != "identifier":
                    continue
                if self.parser._node_text(left, text.encode()) != variable:
                    continue
                if right.type == "call":
                    fn = right.child_by_field_name("function")
                    if fn and fn.type == "identifier":
                        return self._resolve_name(
                            self.parser._node_text(fn, text.encode())
                        )
        return None

    @staticmethod
    def _resolution_method(node) -> str:
        if node.type == "identifier":
            return "name"
        if node.type == "attribute":
            return "attribute"
        return "unknown"


# ======================================================================
# Tree-sitter DEF/USE + data-flow analyzer
# ======================================================================


class _TreeSitterDataFlowAnalyzer:
    """Conservative intra-procedural DEF/USE analysis.

    This deliberately does not pretend to be a full CFG/fixed-point data-flow
    engine. It is the same useful MVP level as the previous AST parser:
    source-order local definitions with statement-level DEF/USE metadata.
    """

    def __init__(self, *, parser: PythonParser, parsed: ParsedRepository, parsed_file: _ParsedFile):
        self.parser = parser
        self.parsed = parsed
        self.parsed_file = parsed_file
        self.record = parsed_file.record
        self.source = parsed_file.source
        self.relations: list[Relation] = []
        self.statement_by_span = {
            (e.start_line, e.end_line): e
            for e in parsed.entities
            if e.type == EntityType.STATEMENT
            and e.path == self.record.relative_path
        }

    def run(self) -> None:
        self._walk_scope(self.parsed_file.tree.root_node, {})

    def _walk_scope(self, node, last_definition: dict[str, Optional[CodeEntity]]):
        # File/module scope.
        for child in node.named_children:
            if child.type in {"function_definition", "async_function_definition"}:
                self._walk_function(child)
            elif child.type == "decorated_definition":
                definition = self.parser._first_child_of_types(child, DEFINITION_TYPES)
                if definition and definition.type in {"function_definition", "async_function_definition"}:
                    self._walk_function(definition)
                elif definition and definition.type == "class_definition":
                    self._walk_class(definition)
            elif child.type == "class_definition":
                self._walk_class(child)
            elif child.type in STATEMENT_TYPES:
                self._process_statement(child, last_definition)

    def _walk_class(self, node) -> None:
        body = node.child_by_field_name("body")
        if body is None:
            return
        # Class-level definitions don't flow into method locals.
        for child in body.named_children:
            if child.type in {"function_definition", "async_function_definition"}:
                self._walk_function(child)
            elif child.type == "decorated_definition":
                definition = self.parser._first_child_of_types(child, DEFINITION_TYPES)
                if definition and definition.type in {"function_definition", "async_function_definition"}:
                    self._walk_function(definition)

    def _walk_function(self, node) -> None:
        definitions: dict[str, Optional[CodeEntity]] = {}
        parameters = node.child_by_field_name("parameters")
        if parameters:
            for child in parameters.named_children:
                if child.type == "identifier":
                    definitions[self.parser._node_text(child, self.source)] = None
                elif child.type in {"typed_parameter", "default_parameter", "typed_default_parameter", "list_splat_pattern", "dictionary_splat_pattern"}:
                    name_node = child.child_by_field_name("name")
                    if name_node is None and child.named_children:
                        name_node = child.named_children[0]
                    if name_node and name_node.type == "identifier":
                        definitions[self.parser._node_text(name_node, self.source)] = None

        body = node.child_by_field_name("body")
        if body is None:
            return
        for child in body.named_children:
            if child.type in {"function_definition", "async_function_definition", "class_definition", "decorated_definition"}:
                # Nested defs are separate scopes.
                if child.type == "class_definition":
                    self._walk_class(child)
                elif child.type == "decorated_definition":
                    definition = self.parser._first_child_of_types(child, DEFINITION_TYPES)
                    if definition:
                        if definition.type == "class_definition":
                            self._walk_class(definition)
                        else:
                            self._walk_function(definition)
                else:
                    self._walk_function(child)
                continue
            if child.type in STATEMENT_TYPES:
                self._process_statement(child, definitions)

    def _process_statement(self, node, last_definition: dict[str, Optional[CodeEntity]]):
        entity = self.statement_by_span.get((
            node.start_point[0] + 1,
            node.end_point[0] + 1,
        ))
        if entity is None:
            return

        uses, defines = self._extract_def_use(node)
        entity.metadata["uses"] = sorted(uses)
        entity.metadata["defines"] = sorted(defines)

        # Resolve uses against definitions that existed before this statement.
        for name in sorted(uses):
            definition = last_definition.get(name, "__UNDEFINED__")
            if definition not in (None, "__UNDEFINED__"):
                self.relations.append(Relation(
                    source_id=definition.id,
                    target_id=entity.id,
                    type=RelationType.DATAFLOW_DEF_USE,
                    metadata={"variable": name, "direction": "def_to_use"},
                ))

        # Definitions become available after the statement.
        for name in defines:
            last_definition[name] = entity

        # Descend into compound statement bodies. The parent statement itself
        # remains the statement representing the condition/header.
        for child in self._nested_statement_children(node):
            self._process_statement(child, last_definition)

    def _extract_def_use(self, node):
        uses: set[str] = set()
        defines: set[str] = set()

        if node.type == "expression_statement":
            children = node.named_children

            if len(children) == 1 and children[0].type in {
                "assignment",
                "augmented_assignment",
            }:
                return self._extract_def_use(children[0])
    
        if node.type == "assignment":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left:
                defines.update(self._store_names(left))
            if right:
                uses.update(self._load_names(right))
            return uses, defines

        if node.type == "augmented_assignment":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left:
                names = self._load_names(left)
                uses.update(names)
                defines.update(self._store_names(left))
            if right:
                uses.update(self._load_names(right))
            return uses, defines

        if node.type == "for_statement":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left:
                defines.update(self._store_names(left))
            if right:
                uses.update(self._load_names(right))
            return uses, defines

        if node.type in {"import_statement", "import_from_statement"}:
            # Imports define their local aliases. Detailed import edges are
            # handled separately.
            if node.type == "import_statement":
                for child in node.named_children:
                    if child.type == "aliased_import":
                        alias = child.child_by_field_name("alias")
                        name = child.child_by_field_name("name")
                        local = alias or name
                        if local:
                            defines.add(self.parser._node_text(local, self.source).split(".")[0])
                    elif child.type == "dotted_name":
                        defines.add(self.parser._node_text(child, self.source).split(".")[0])
            return uses, defines

        if node.type == "with_statement":
            for child in node.named_children:
                if child.type == "with_clause":
                    uses.update(self._load_names(child))
                elif child.type in {"as_pattern", "as_pattern_target"}:
                    defines.update(self._store_names(child))
            return uses, defines

        # For return/if/while/expression/raise/assert/etc., every identifier
        # is a use unless it occurs in a store position under an assignment.
        uses.update(self._load_names(node))
        return uses, defines

    def _load_names(self, node):
        result = set()
        for current in PythonParser._walk_named(node):
            if current.type != "identifier":
                continue
            if self._is_assignment_target(current):
                continue
            result.add(self.parser._node_text(current, self.source))
        return result

    def _store_names(self, node):
        result = set()
        for current in PythonParser._walk_named(node):
            if current.type == "identifier":
                result.add(self.parser._node_text(current, self.source))
        return result

    def _is_assignment_target(self, identifier) -> bool:
        parent = identifier.parent
        if parent is None:
            return False
        # Walk up through patterns until the relevant assignment node.
        current = parent
        for _ in range(6):
            if current is None:
                return False
            if current.type in {"assignment", "augmented_assignment", "for_statement"}:
                left = current.child_by_field_name("left")
                return left is not None and self._contains_node(left, identifier)
            if current.type in {"return_statement", "expression_statement", "call"}:
                return False
            current = current.parent
        return False

    @staticmethod
    def _contains_node(root, needle) -> bool:
        if root.id == needle.id:
            return True
        return any(_TreeSitterDataFlowAnalyzer._contains_node(c, needle) for c in root.named_children)

    def _nested_statement_children(self, node):
        result = []
        for child in node.named_children:
            if child.type in DEFINITION_TYPES or child.type == "decorated_definition":
                continue
            if child.type in STATEMENT_TYPES:
                result.append(child)
            elif child.type in {
                "block", "else_clause", "elif_clause", "finally_clause",
                "except_clause", "case_clause",
            }:
                for nested in child.named_children:
                    if nested.type in STATEMENT_TYPES:
                        result.append(nested)
        return result
