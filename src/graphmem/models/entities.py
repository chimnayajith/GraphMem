from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EntityType(str, Enum):
    REPOSITORY = "repository"
    DIRECTORY = "directory"
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    STATEMENT = "statement"


@dataclass
class CodeEntity:
    """
    A node in GraphMem's repository intelligence model.
    """

    id: str
    type: EntityType
    name: str

    path: str | None = None
    qualified_name: str | None = None

    start_line: int | None = None
    end_line: int | None = None

    parent_id: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)