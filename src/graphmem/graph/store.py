from abc import ABC, abstractmethod

from graphmem.models.entities import CodeEntity
from graphmem.models.relations import Relation


class GraphStore(ABC):

    @abstractmethod
    def add_entity(self, entity: CodeEntity) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_relation(self, relation: Relation) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_entity(self, entity_id: str) -> CodeEntity | None:
        raise NotImplementedError

    @abstractmethod
    def neighbors(
        self,
        entity_id: str,
    ) -> list[CodeEntity]:
        raise NotImplementedError