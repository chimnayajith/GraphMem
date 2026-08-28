from abc import ABC, abstractmethod
from pathlib import Path

from graphmem.models.repository import ParsedRepository


class BaseParser(ABC):

    @abstractmethod
    def parse(self, repository_path: Path) -> ParsedRepository:
        """
        Parse a repository and return its entities and relationships.
        """
        raise NotImplementedError