"""Common interface every language parser must implement.

Per ADR-19 (Language Extensibility Through Adapters), the rest of
GraphMem (graph store, retrieval, agent tools) must never depend on
language-specific AST details. Each parser only needs to:

    1. walk a repository directory,
    2. emit CodeEntity / Relation objects using the shared schema in
       graphmem.models,
    3. return them wrapped in a ParsedRepository.

    LanguageParser
    ├── PythonParser   (this milestone)
    ├── JavaParser     (later, per ADR-19)
    └── ...
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from graphmem.models import ParsedRepository


class LanguageParser(ABC):
    """Abstract base class for all per-language repository parsers."""

    #: Overridden by subclasses, e.g. "python". Used in CodeEntity.language
    #: and for file-extension based dispatch by callers that support
    #: multiple languages at once.
    language: str = "unknown"

    @abstractmethod
    def parse_repository(self, repository_path: str) -> ParsedRepository:
        """Parse an entire repository and return the extracted graph data.

        Implementations should be conservative about edge creation
        (ADR-06): prefer omitting an edge over guessing one.
        """
        raise NotImplementedError

    # ----------------------------------------------------------------
    # Shared helpers available to every subclass.
    # ----------------------------------------------------------------

    @staticmethod
    def resolve_repo_name(repository_path: str) -> str:
        """The name used in generated entity IDs, e.g. 'my_repo'."""
        return Path(repository_path).resolve().name or "repo"

    @staticmethod
    def resolve_version(repository_path: str) -> str:
        """Best-effort repository version string for entity IDs (ADR-14).

        Uses the current git commit SHA when the path is inside a git
        repository with at least one commit; falls back to "working"
        for a plain directory or a commit-less repo. Never raises -
        parsing must not fail just because git metadata isn't
        available.
        """
        try:
            result = subprocess.run(
                ["git", "-C", str(repository_path), "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            sha = result.stdout.strip()
            if result.returncode == 0 and sha:
                return sha
        except (OSError, subprocess.SubprocessError):
            pass
        return "working"

    @staticmethod
    def make_entity_id(
        repo_name: str,
        relative_path: str,
        version: str,
        qualified_name: Optional[str] = None,
    ) -> str:
        """Build a stable entity ID per the ADR-14 format::

            repo://<repo_name>/<relative_path>[::<qualified_name>]@<version>
        """
        relative_path = relative_path.replace("\\", "/")
        base = f"repo://{repo_name}/{relative_path}"
        if qualified_name:
            base += f"::{qualified_name}"
        return f"{base}@{version}"
