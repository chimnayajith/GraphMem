from dataclasses import dataclass, field

from graphmem.models.entities import CodeEntity
from graphmem.models.relations import Relation


@dataclass
class ParsedRepository:
    repository_path: str

    entities: list[CodeEntity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)

    def add_entity(self, entity: CodeEntity) -> None:
        self.entities.append(entity)

    def add_relation(self, relation: Relation) -> None:
        self.relations.append(relation)