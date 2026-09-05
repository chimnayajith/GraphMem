from graphmem.parsing.python_parser import PythonParser
from graphmem.graph.builder import GraphBuilder
from graphmem.retrieval.candidates import generate_candidates
from graphmem.ranking.ranker import rank_candidates


REPOSITORY_PATH = "examples/sample_repo"

ISSUE = "Formatter has a bug in formatting output"


def main():

    print("\n=== PARSING REPOSITORY ===\n")

    parser = PythonParser()

    parsed = parser.parse_repository(
        REPOSITORY_PATH
    )

    print(f"Entities: {len(parsed.entities)}")
    print(f"Relations: {len(parsed.relations)}")

    print("\n=== BUILDING GRAPH ===\n")

    graph = GraphBuilder().build(parsed)

    print("Graph built successfully.")

    print("\n=== GENERATING CANDIDATES ===\n")

    candidates = generate_candidates(
        issue=ISSUE,
        entities=parsed.entities,
        graph=graph,
        seed_limit=5,
        max_depth=2,
    )

    print(f"Candidates generated: {len(candidates)}")

    print("\n=== RANKING CANDIDATES ===\n")

    ranked = rank_candidates(candidates)

    for i, candidate in enumerate(ranked, start=1):

        entity = candidate.entity

        print(
            f"{i}. [{entity.type.value}] "
            f"{entity.qualified_name or entity.name}"
        )

        print(f"   Path: {entity.path}")
        print(f"   Score: {candidate.score:.3f}")
        print(f"   Lexical score: {candidate.lexical_score:.3f}")
        print(f"   Graph score: {candidate.graph_score:.3f}")
        print(f"   Depth: {candidate.depth}")
        print(f"   Evidence: {', '.join(candidate.evidence)}")

        print()


if __name__ == "__main__":
    main()