"""Language parsers: source code -> CodeEntity / Relation objects.

    from graphmem.parsing import PythonParser

    parser = PythonParser()
    parsed_repo = parser.parse_repository("/path/to/repo")
"""

from graphmem.parsing.base import LanguageParser
from graphmem.parsing.python_parser import PythonParser

__all__ = ["LanguageParser", "PythonParser"]
