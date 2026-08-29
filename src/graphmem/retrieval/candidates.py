import re
from dataclasses import dataclass

from graphmem.graph.store import GraphStore
from graphmem.models.entities import CodeEntity
from graphmem.retrieval.traversal import expand_from_seed


@dataclass
class Candidate:
    entity: CodeEntity

    lexical_score: float
    graph_score: float

    depth: int

    path: list[str]

    evidence: list[str]

    score: float = 0.0


STOP_WORDS = {
    "the",
    "a",
    "an",
    "to",
    "is",
    "are",
    "and",
    "or",
    "of",
    "in",
    "on",
    "when",
    "with",
}


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text.lower())
    return [w for w in words if w not in STOP_WORDS]


def lexical_score(query: str, entity: CodeEntity) -> float:
    query_tokens = set(tokenize(query))

    if not query_tokens:
        return 0.0

    searchable = " ".join(
        [
            entity.name or "",
            entity.qualified_name or "",
            entity.path or "",
        ]
    )

    entity_tokens = set(tokenize(searchable))

    matches = query_tokens & entity_tokens

    return len(matches) / len(query_tokens)


def generate_candidates(
    issue: str,
    entities: list[CodeEntity],
    graph: GraphStore,
    seed_limit: int = 5,
    max_depth: int = 2,
) -> list[Candidate]:

    # ----- Stage 1 : lexical search -----

    ranked = sorted(
        entities,
        key=lambda entity: lexical_score(issue, entity),
        reverse=True,
    )

    seeds = [
        entity
        for entity in ranked[:seed_limit]
        if lexical_score(issue, entity) > 0
    ]

    # ----- Stage 2 : graph expansion -----

    candidates: dict[str, Candidate] = {}

    for seed in seeds:

        traversal = expand_from_seed(
            graph,
            seed,
            max_depth,
        )

        for result in traversal:

            entity = result.entity

            lex = lexical_score(issue, entity)

            graph_score = 1 / (result.depth + 1)

            evidence = []

            if lex > 0:
                evidence.append("lexical match")

            if result.depth == 0:
                evidence.append("seed entity")
            else:
                evidence.append(
                    f"{result.depth}-hop graph traversal"
                )

            existing = candidates.get(entity.id)

            if (
                existing is None
                or graph_score > existing.graph_score
            ):
                candidates[entity.id] = Candidate(
                    entity=entity,
                    lexical_score=lex,
                    graph_score=graph_score,
                    depth=result.depth,
                    path=result.path,
                    evidence=evidence,
                )

    return list(candidates.values())