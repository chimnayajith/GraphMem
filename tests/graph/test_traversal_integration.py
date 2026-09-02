from graphmem.graph.builder import GraphBuilder
from graphmem.models.entities import CodeEntity, EntityType
from graphmem.models.relations import Relation, RelationType
from graphmem.models.repository import ParsedRepository
from graphmem.retrieval.traversal import expand_from_seed


def test_graphmem_traversal():

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

    function_a = CodeEntity(
        id="function:parser.py:parse",
        type=EntityType.FUNCTION,
        name="parse",
        path="parser.py",
    )

    function_b = CodeEntity(
        id="function:parser.py:validate",
        type=EntityType.FUNCTION,
        name="validate",
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
            target_id=function_a.id,
            type=RelationType.CONTAINS,
        ),
        Relation(
            source_id=file.id,
            target_id=function_b.id,
            type=RelationType.CONTAINS,
        ),
    ]

    parsed_repository = ParsedRepository(
        repository_path="test",
        entities=[
            repository,
            file,
            function_a,
            function_b,
        ],
        relations=relations,
    )

    graph = GraphBuilder().build(parsed_repository)

    results = expand_from_seed(
        graph,
        function_a,
        max_depth=2,
    )

    result_ids = {
        result.entity.id
        for result in results
    }

    assert function_a.id in result_ids
    assert file.id in result_ids
    assert repository.id in result_ids
    assert function_b.id in result_ids