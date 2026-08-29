from dataclasses import dataclass

from graphmem.retrieval.candidates import Candidate


@dataclass
class RankWeights:
    lexical: float = 0.7
    graph: float = 0.3


def rank_candidates(
    candidates: list[Candidate],
    weights: RankWeights | None = None,
) -> list[Candidate]:
    """
    Rank candidates using lexical and graph relevance.

    Final score:

        lexical_weight * lexical_score
        + graph_weight * graph_score
    """

    if weights is None:
        weights = RankWeights()

    total_weight = weights.lexical + weights.graph

    if total_weight <= 0:
        raise ValueError(
            "Ranking weights must sum to a positive value."
        )

    lexical_weight = weights.lexical / total_weight
    graph_weight = weights.graph / total_weight

    for candidate in candidates:
        candidate.score = (
            lexical_weight * candidate.lexical_score
            + graph_weight * candidate.graph_score
        )

    candidates.sort(
        key=lambda candidate: candidate.score,
        reverse=True,
    )

    return candidates
