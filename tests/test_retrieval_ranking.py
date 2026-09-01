from graphmem.models.entities import CodeEntity, EntityType
from graphmem.retrieval.traversal import expand_from_seed
from graphmem.retrieval.candidates import generate_candidates
from graphmem.ranking.ranker import (
    RankWeights,
    rank_candidates,
)


class MockGraph:
    def __init__(self, graph):
        self.graph = graph

    def neighbors(self, entity_id):
        return self.graph.get(entity_id, [])


def make_entities():
    parser = CodeEntity(
        id="1",
        type=EntityType.CLASS,
        name="Parser",
        path="src/parser.py",
        qualified_name="Parser",
    )

    parse = CodeEntity(
        id="2",
        type=EntityType.METHOD,
        name="parse",
        path="src/parser.py",
        qualified_name="Parser.parse",
    )

    tokenize = CodeEntity(
        id="3",
        type=EntityType.FUNCTION,
        name="tokenize",
        path="src/tokenizer.py",
        qualified_name="tokenize",
    )

    return parser, parse, tokenize


def test_graph_traversal():

    parser, parse, tokenize = make_entities()

    graph = MockGraph({
        "1": [parse],
        "2": [tokenize],
        "3": [],
    })

    results = expand_from_seed(
        graph,
        parser,
        max_depth=2,
    )

    ids = [result.entity.id for result in results]

    assert ids == ["1", "2", "3"]


def test_graph_depth():

    parser, parse, tokenize = make_entities()

    graph = MockGraph({
        "1": [parse],
        "2": [tokenize],
        "3": [],
    })

    results = expand_from_seed(
        graph,
        parser,
        max_depth=2,
    )

    depths = {
        result.entity.id: result.depth
        for result in results
    }

    assert depths["1"] == 0
    assert depths["2"] == 1
    assert depths["3"] == 2


def test_candidate_generation():

    parser, parse, tokenize = make_entities()

    graph = MockGraph({
        "1": [parse],
        "2": [tokenize],
        "3": [],
    })

    candidates = generate_candidates(
        issue="Parser parse error",
        entities=[
            parser,
            parse,
            tokenize,
        ],
        graph=graph,
        seed_limit=5,
        max_depth=2,
    )

    ids = {
        candidate.entity.id
        for candidate in candidates
    }

    assert "1" in ids
    assert "2" in ids
    assert "3" in ids


def test_ranking():

    parser, parse, tokenize = make_entities()

    graph = MockGraph({
        "1": [parse],
        "2": [tokenize],
        "3": [],
    })

    candidates = generate_candidates(
        issue="Parser parse error",
        entities=[
            parser,
            parse,
            tokenize,
        ],
        graph=graph,
    )

    ranked = rank_candidates(candidates)

    assert all(
        0.0 <= candidate.score <= 1.0
        for candidate in ranked
    )

    assert all(
        ranked[i].score >= ranked[i + 1].score
        for i in range(len(ranked) - 1)
    )


def test_graph_evidence():

    parser, parse, tokenize = make_entities()

    graph = MockGraph({
        "1": [parse],
        "2": [tokenize],
        "3": [],
    })

    candidates = generate_candidates(
        issue="Parser parse error",
        entities=[
            parser,
            parse,
            tokenize,
        ],
        graph=graph,
    )

    tokenize_candidate = next(
        candidate
        for candidate in candidates
        if candidate.entity.id == "3"
    )

    assert "1-hop graph traversal" in (
        tokenize_candidate.evidence
    )
def test_custom_ranking_weights():

    parser, parse, tokenize = make_entities()

    graph = MockGraph({
        "1": [parse],
        "2": [tokenize],
        "3": [],
    })

    candidates = generate_candidates(
        issue="Parser parse error",
        entities=[
            parser,
            parse,
            tokenize,
        ],
        graph=graph,
    )

    ranked = rank_candidates(
        candidates,
        weights=RankWeights(
            lexical=0.9,
            graph=0.1,
        ),
    )

    assert ranked[0].score >= ranked[-1].score