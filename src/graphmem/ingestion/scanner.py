from pathlib import Path

from graphmem.models.repository import ParsedRepository
from graphmem.parsing.python_parser import PythonParser


class RepositoryScanner:
    """Detect the languages present in a repository."""

    SUPPORTED_EXTENSIONS = {
        ".py": "python",
    }

    def __init__(self, repository_path: str):
        self.repository_path = Path(repository_path).expanduser().resolve()

    def validate(self) -> None:
        if not self.repository_path.exists():
            raise FileNotFoundError(
                f"Repository does not exist: {self.repository_path}"
            )

        if not self.repository_path.is_dir():
            raise NotADirectoryError(
                f"Repository path is not a directory: {self.repository_path}"
            )

    def detect_languages(self) -> set[str]:
        self.validate()

        languages = set()

        for path in self.repository_path.rglob("*"):
            if not path.is_file():
                continue

            language = self.SUPPORTED_EXTENSIONS.get(path.suffix.lower())

            if language:
                languages.add(language)

        return languages

    def get_parser(self):
        languages = self.detect_languages()

        if not languages:
            raise ValueError(
                "No supported source files found in repository."
            )

        unsupported = languages - {"python"}

        if unsupported:
            raise ValueError(
                f"Unsupported languages detected: {sorted(unsupported)}"
            )

        return PythonParser()

    def parse(self) -> ParsedRepository:
        parser = self.get_parser()
        return parser.parse_repository(str(self.repository_path))