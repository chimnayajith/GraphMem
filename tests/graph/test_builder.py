from graphmem.graph.builder import GraphBuilder
from graphmem.models.entities import CodeEntity, EntityType
from graphmem.models.relations import Relation, RelationType
from graphmem.models.repository import ParsedRepository


def test_build_graph():

    repository = CodeEntity(
        id="repository:test",
        type=EntityType.REPOSITORY,
        name="test",
    )

    file = CodeEntity(
        id="file:parser.py",
        type=EntityType.FILE,
        name="parser.py",
        path="parser.py",
    )

    function = CodeEntity(
        id="function:parser.py:parse",
        type=EntityType.FUNCTION,
        name="parse",
        path="parser.py",
    )

    relations = [
        Relation(
            source_id=repository.id,
            target_id=file.id,
            type=RelationType.CONTAINS,
        ),
        Relation(
            source_id=file.id,
            target_id=function.id,
            type=RelationType.CONTAINS,
        ),
    ]

    parsed_repository = ParsedRepository(
        repository_path="test",
        entities=[
            repository,
            file,
            function,
        ],
        relations=relations,
    )

    graph = GraphBuilder().build(parsed_repository)

    assert graph.get_entity(repository.id) == repository

    neighbors = graph.neighbors(file.id)

    assert function in neighbors
    assert repository in neighbors