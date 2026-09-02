from graphmem.indexing.entity_index import EntityIndex
from graphmem.models.entities import CodeEntity, EntityType
from graphmem.indexing.bm25_index import BM25Index
from graphmem.retrieval.search import SearchEngine


def test_entity_index_exact_search():
    entities = [
        CodeEntity(
            id="1",
            type=EntityType.CLASS,
            name="Parser",
            path="src/parser.py",
            qualified_name="Parser",
        ),
        CodeEntity(
            id="2",
            type=EntityType.METHOD,
            name="parse",
            path="src/parser.py",
            qualified_name="Parser.parse",
        ),
    ]

    index = EntityIndex(entities)

    results = index.search("Parser")

    assert [entity.id for entity in results] == ["1"]


def test_entity_index_qualified_name_search():
    entities = [
        CodeEntity(
            id="1",
            type=EntityType.CLASS,
            name="Parser",
            path="src/parser.py",
            qualified_name="Parser",
        ),
        CodeEntity(
            id="2",
            type=EntityType.METHOD,
            name="parse",
            path="src/parser.py",
            qualified_name="Parser.parse",
        ),
    ]

    index = EntityIndex(entities)

    results = index.search("Parser.parse")

    assert [entity.id for entity in results] == ["2"]



def test_entity_index_path_search():
    entities = [
        CodeEntity(
            id="1",
            type=EntityType.CLASS,
            name="Parser",
            path="src/parser.py",
            qualified_name="Parser",
        ),
        CodeEntity(
            id="2",
            type=EntityType.METHOD,
            name="parse",
            path="src/parser.py",
            qualified_name="Parser.parse",
        ),
    ]

    index = EntityIndex(entities)

    results = index.search("src/parser.py")

    assert [entity.id for entity in results] == ["1", "2"]



def test_bm25_search():
    entities = [
        CodeEntity(
            id="1",
            type=EntityType.CLASS,
            name="Parser",
            path="src/parser.py",
            qualified_name="Parser",
        ),
        CodeEntity(
            id="2",
            type=EntityType.METHOD,
            name="parse",
            path="src/parser.py",
            qualified_name="Parser.parse",
        ),
        CodeEntity(
            id="3",
            type=EntityType.FUNCTION,
            name="tokenize",
            path="src/tokenizer.py",
            qualified_name="tokenize",
        ),
    ]

    index = BM25Index(entities)

    results = index.search("Parser parse error", top_k=3)

    assert results
    assert results[0].id in {"1", "2"}



def test_search_engine_combines_exact_and_bm25():
    entities = [
        CodeEntity(
            id="1",
            type=EntityType.CLASS,
            name="Parser",
            path="src/parser.py",
            qualified_name="Parser",
        ),
        CodeEntity(
            id="2",
            type=EntityType.METHOD,
            name="parse",
            path="src/parser.py",
            qualified_name="Parser.parse",
        ),
        CodeEntity(
            id="3",
            type=EntityType.FUNCTION,
            name="tokenize",
            path="src/tokenizer.py",
            qualified_name="tokenize",
        ),
    ]

    engine = SearchEngine(entities)

    results = engine.search("Parser parse error", top_k=3)

    result_ids = [entity.id for entity in results]

    assert "1" in result_ids
    assert "2" in result_ids
    assert len(result_ids) <= 3