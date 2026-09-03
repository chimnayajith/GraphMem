"""Python repository parser.

    Python Repository
           |
           v
    Python AST Parsing
           |
           v
    CodeEntity objects + Relation objects
           |
           v
    ParsedRepository

Scope of this milestone (see task priority order):

    1. Files
    2. Classes
    3. Functions / Methods
    4. CONTAINS relationships
    5. Basic (repo-local, resolved-only) IMPORTS relationships

Call/inheritance resolution, statement-level nodes, and data-flow are
deliberately out of scope here (owned by later work / other members).

Uses the shared models from graphmem.models (graphmem.models.entities,
graphmem.models.relations, graphmem.models.repository) exclusively -
no separate entity/relation format is defined here. In particular:

* `CodeEntity` has no `language` or `version` field, so both are
  recorded in `entity.metadata` instead (`metadata["language"]`,
  `metadata["version"]`).
* `CodeEntity.path` (not `file_path`) holds the repo-relative source
  path.
* `Relation` has no `confidence`/`source` field, so provenance for
  resolved imports is recorded in `relation.metadata` instead.

Design notes
------------
* Directories are included as first-class DIRECTORY nodes (ADR-03),
  since the CONTAINS hierarchy is otherwise incomplete: without them a
  file two directories deep would have no path back to the repository
  root.
* IMPORTS edges are only created when the imported module resolves to
  another file inside *this* repository. External/library imports are
  kept as plain strings in the file's metadata instead of a graph edge
  (ADR-06 - conservative relationship resolution; ADR-03 - a
  package/directory is not the same thing as a third-party library).
* A file that fails to parse (SyntaxError) still gets a FILE entity so
  the repository hierarchy stays intact; the error is recorded in its
  metadata instead of aborting the whole run.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

from graphmem.models.entities import CodeEntity, EntityType
from graphmem.models.relations import Relation, RelationType
from graphmem.models.repository import ParsedRepository
from graphmem.parsing.base import LanguageParser

#: Directories we never descend into when walking a repository.
DEFAULT_EXCLUDED_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env", ".tox", ".mypy_cache",
    ".pytest_cache", "build", "dist", "node_modules", ".idea", ".vscode",
}


@dataclass
class _FileRecord:
    """Bookkeeping for one source file during parsing."""

    relative_path: str          # posix-style, relative to repo root
    absolute_path: Path
    module_name: str            # dotted module path, e.g. "pkg.sub.mod"
    entity_id: str


class PythonParser(LanguageParser):
    """Parses a Python repository into CodeEntity / Relation objects using `ast`."""

    language = "python"

    def __init__(self, excluded_dirs: Optional[set[str]] = None) -> None:
        self.excluded_dirs = excluded_dirs if excluded_dirs is not None else set(DEFAULT_EXCLUDED_DIRS)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def parse_repository(self, repository_path: str) -> ParsedRepository:
        repo_root = Path(repository_path).resolve()
        if not repo_root.is_dir():
            raise NotADirectoryError(f"Repository path does not exist or is not a directory: {repo_root}")

        repo_name = self.resolve_repo_name(str(repo_root))
        version = self.resolve_version(str(repo_root))

        parsed = ParsedRepository(repository_path=str(repo_root))

        # --- Pass 0: repository root entity ---------------------------------
        repo_entity_id = f"repo://{repo_name}@{version}"
        parsed.add_entity(
            CodeEntity(
                id=repo_entity_id,
                type=EntityType.REPOSITORY,
                name=repo_name,
                metadata={"language": self.language, "version": version},
            )
        )

        # --- Pass 1: discover files, build the directory hierarchy and the
        #     module map used for import resolution -------------------------
        file_records = self._discover_files(repo_root)
        module_map = {rec.module_name: rec for rec in file_records}

        self._build_directory_hierarchy(
            parsed=parsed,
            repo_name=repo_name,
            repo_entity_id=repo_entity_id,
            version=version,
            file_records=file_records,
        )

        for rec in file_records:
            parsed.add_entity(
                CodeEntity(
                    id=rec.entity_id,
                    type=EntityType.FILE,
                    name=PurePosixPath(rec.relative_path).name,
                    path=rec.relative_path,
                    qualified_name=rec.module_name,
                    metadata={"language": self.language, "version": version, "imports": []},
                )
            )

        # --- Pass 2: parse each file's AST for classes/functions/methods
        #     and imports -----------------------------------------------------
        for rec in file_records:
            self._parse_file(rec, repo_name, version, module_map, parsed)

        return parsed

    # ------------------------------------------------------------------
    # Repository discovery
    # ------------------------------------------------------------------

    def _discover_files(self, repo_root: Path) -> list[_FileRecord]:
        records: list[_FileRecord] = []
        repo_name = self.resolve_repo_name(str(repo_root))
        version = self.resolve_version(str(repo_root))

        for path in sorted(repo_root.rglob("*.py")):
            if any(part in self.excluded_dirs for part in path.relative_to(repo_root).parts):
                continue
            relative_path = path.relative_to(repo_root).as_posix()
            module_name = self._module_name_for(relative_path)
            entity_id = self.make_entity_id(repo_name, relative_path, version)
            records.append(
                _FileRecord(
                    relative_path=relative_path,
                    absolute_path=path,
                    module_name=module_name,
                    entity_id=entity_id,
                )
            )
        return records

    @staticmethod
    def _module_name_for(relative_path: str) -> str:
        """Dotted module path for a repo-relative file path.

        'pkg/sub/mod.py' -> 'pkg.sub.mod'
        'pkg/__init__.py' -> 'pkg'
        'mod.py' -> 'mod'
        """
        parts = relative_path.split("/")
        parts[-1] = parts[-1][: -len(".py")]  # strip extension
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def _build_directory_hierarchy(
        self,
        *,
        parsed: ParsedRepository,
        repo_name: str,
        repo_entity_id: str,
        version: str,
        file_records: list[_FileRecord],
    ) -> None:
        """Create DIRECTORY entities for every directory that (transitively)
        contains a parsed file, plus CONTAINS edges down to files.

        NOTE: every path here is manipulated as a posix-style string
        (forward slashes), matching `_FileRecord.relative_path` and the
        `path` field stored on entities. `pathlib.Path(...)` must NOT be
        used for this bookkeeping on its own: on Windows it silently
        renders back out with backslashes, which desyncs sorting/dict
        lookups keyed on forward slashes. `PurePosixPath` stays on "/"
        regardless of host OS.
        """
        directory_paths: set[str] = set()
        for rec in file_records:
            parent = PurePosixPath(rec.relative_path).parent.as_posix()
            while parent not in (".", ""):
                directory_paths.add(parent)
                parent = PurePosixPath(parent).parent.as_posix()

        dir_entity_id = {"": repo_entity_id}
        for dir_path in sorted(directory_paths, key=lambda p: p.count("/")):
            entity_id = self.make_entity_id(repo_name, dir_path, version)
            dir_entity_id[dir_path] = entity_id
            parsed.add_entity(
                CodeEntity(
                    id=entity_id,
                    type=EntityType.DIRECTORY,
                    name=PurePosixPath(dir_path).name,
                    path=dir_path,
                    metadata={"language": self.language, "version": version},
                )
            )
            parent_dir = PurePosixPath(dir_path).parent.as_posix()
            parent_dir = "" if parent_dir == "." else parent_dir
            parsed.add_relation(
                Relation(
                    source_id=dir_entity_id[parent_dir],
                    target_id=entity_id,
                    type=RelationType.CONTAINS,
                )
            )

        for rec in file_records:
            parent_dir = PurePosixPath(rec.relative_path).parent.as_posix()
            parent_dir = "" if parent_dir == "." else parent_dir
            parsed.add_relation(
                Relation(
                    source_id=dir_entity_id.get(parent_dir, repo_entity_id),
                    target_id=rec.entity_id,
                    type=RelationType.CONTAINS,
                )
            )

    # ------------------------------------------------------------------
    # Per-file parsing
    # ------------------------------------------------------------------

    def _parse_file(
        self,
        rec: _FileRecord,
        repo_name: str,
        version: str,
        module_map: dict[str, _FileRecord],
        parsed: ParsedRepository,
    ) -> None:
        file_entity = parsed.get_entity(rec.entity_id)
        assert file_entity is not None  # created in pass 1

        try:
            source = rec.absolute_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            file_entity.metadata["read_error"] = str(exc)
            return

        try:
            tree = ast.parse(source, filename=rec.relative_path)
        except SyntaxError as exc:
            file_entity.metadata["parse_error"] = f"{exc.__class__.__name__}: {exc}"
            return

        # Classes / functions / methods + CONTAINS.
        visitor = _DefinitionVisitor(
            repo_name=repo_name,
            version=version,
            language=self.language,
            rec=rec,
            make_entity_id=self.make_entity_id,
        )
        visitor.visit(tree)
        for entity in visitor.entities:
            parsed.add_entity(entity)
        for relation in visitor.relations:
            parsed.add_relation(relation)

        # Imports (module-level and nested, but always resolved at file
        # granularity - see module docstring).
        self._extract_imports(tree, rec, module_map, file_entity, parsed)

    def _extract_imports(
        self,
        tree: ast.AST,
        rec: _FileRecord,
        module_map: dict[str, _FileRecord],
        file_entity: CodeEntity,
        parsed: ParsedRepository,
    ) -> None:
        current_package = rec.module_name.rsplit(".", 1)[0] if "." in rec.module_name else ""
        # A package's own __init__.py IS the package, so imports inside it
        # resolve relative to itself, not its parent.
        if rec.absolute_path.name == "__init__.py":
            current_package = rec.module_name

        resolved_targets: set[str] = set()  # dedup edges within this file

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                raw = self._unparse(node)
                file_entity.metadata["imports"].append(raw)
                for alias in node.names:
                    candidate = alias.name
                    target = module_map.get(candidate)
                    if target is not None and target.entity_id != rec.entity_id:
                        resolved_targets.add(target.entity_id)

            elif isinstance(node, ast.ImportFrom):
                raw = self._unparse(node)
                file_entity.metadata["imports"].append(raw)

                base_module = self._resolve_relative_module(
                    current_package=current_package,
                    node_module=node.module,
                    level=node.level,
                )

                matched_any = False
                for alias in node.names:
                    candidate = f"{base_module}.{alias.name}" if base_module else alias.name
                    target = module_map.get(candidate)
                    if target is not None and target.entity_id != rec.entity_id:
                        resolved_targets.add(target.entity_id)
                        matched_any = True

                if not matched_any and base_module:
                    target = module_map.get(base_module)
                    if target is not None and target.entity_id != rec.entity_id:
                        resolved_targets.add(target.entity_id)

        for target_id in resolved_targets:
            parsed.add_relation(
                Relation(
                    source_id=rec.entity_id,
                    target_id=target_id,
                    type=RelationType.IMPORTS,
                    metadata={"resolved_via": "module_path_match"},
                )
            )

    @staticmethod
    def _resolve_relative_module(current_package: str, node_module: Optional[str], level: int) -> Optional[str]:
        """Resolve an (absolute or relative) import target to a dotted module path.

        `level` is 0 for absolute imports (`from a.b import c`) and 1+ for
        relative imports (`from . import c` -> level 1, `from .. import c`
        -> level 2, ...).
        """
        if level == 0:
            return node_module

        parts = current_package.split(".") if current_package else []
        # level=1 means "stay in the current package"; each extra level
        # strips one more component.
        strip = level - 1
        parts = parts[: len(parts) - strip] if strip <= len(parts) else []
        base = ".".join(parts)
        if node_module:
            return f"{base}.{node_module}" if base else node_module
        return base or None

    @staticmethod
    def _unparse(node: ast.AST) -> str:
        try:
            return ast.unparse(node)
        except Exception:  # pragma: no cover - defensive, ast.unparse is 3.9+
            return node.__class__.__name__


class _DefinitionVisitor(ast.NodeVisitor):
    """Walks one file's AST, emitting CLASS/FUNCTION/METHOD entities and
    CONTAINS edges. Import handling lives in PythonParser, not here, since
    imports are resolved at file granularity regardless of nesting.
    """

    def __init__(self, *, repo_name: str, version: str, language: str, rec: _FileRecord, make_entity_id):
        self.repo_name = repo_name
        self.version = version
        self.language = language
        self.rec = rec
        self.make_entity_id = make_entity_id

        self.entities: list[CodeEntity] = []
        self.relations: list[Relation] = []

        # Stack of (entity_id, qualified_name_parts, is_class).
        self._scope_stack: list[tuple[str, list[str], bool]] = [
            (rec.entity_id, [], False)
        ]

    def _current_parent(self) -> tuple[str, list[str], bool]:
        return self._scope_stack[-1]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add_definition(node, EntityType.CLASS, is_class=True)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add_definition(node, self._function_entity_type(), is_class=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._add_definition(node, self._function_entity_type(), is_class=False)

    def _function_entity_type(self) -> EntityType:
        _, _, parent_is_class = self._current_parent()
        return EntityType.METHOD if parent_is_class else EntityType.FUNCTION

    def _add_definition(self, node, entity_type: EntityType, *, is_class: bool) -> None:
        parent_id, parent_qual_parts, _ = self._current_parent()
        qualified_parts = parent_qual_parts + [node.name]
        qualified_name = ".".join(qualified_parts)

        entity_id = self.make_entity_id(
            self.repo_name, self.rec.relative_path, self.version, qualified_name=qualified_name
        )

        decorators = [self._decorator_name(d) for d in getattr(node, "decorator_list", [])]
        metadata: dict = {
            "language": self.language,
            "version": self.version,
            "decorators": decorators,
        }
        if is_class:
            metadata["bases"] = [self._decorator_name(b) for b in node.bases]

        entity = CodeEntity(
            id=entity_id,
            type=entity_type,
            name=node.name,
            path=self.rec.relative_path,
            qualified_name=qualified_name,
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            parent_id=parent_id,
            metadata=metadata,
        )
        self.entities.append(entity)
        self.relations.append(
            Relation(source_id=parent_id, target_id=entity_id, type=RelationType.CONTAINS)
        )

        self._scope_stack.append((entity_id, qualified_parts, is_class))
        self.generic_visit(node)
        self._scope_stack.pop()

    @staticmethod
    def _decorator_name(node: ast.AST) -> str:
        try:
            return ast.unparse(node)
        except Exception:  # pragma: no cover - defensive
            return node.__class__.__name__
