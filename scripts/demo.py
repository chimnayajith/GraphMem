from graphmem.parsing.python_parser import PythonParser
from graphmem.graph.builder import GraphBuilder
from graphmem.indexing.search import SearchEngine
from graphmem.retrieval.candidates import generate_candidates
from graphmem.ranking.ranker import rank_candidates


REPOSITORY_PATH = "examples/sample_repo"

ISSUE = """
Authentication fails when a user tries to log in.
"""


def main():

    print("Parsing repository...")

    parser = PythonParser()

    parsed_repository = parser.parse_repository(
        REPOSITORY_PATH
    )

    print(
        f"Found {len(parsed_repository.entities)} entities"
    )

    print(
        f"Found {len(parsed_repository.relations)} relations"
    )

    print("\nBuilding graph...")

    graph = GraphBuilder().build(
        parsed_repository
    )

    print("Graph built.")

    print("\nSearching repository...")

    search_engine = SearchEngine(
        parsed_repository.entities
    )

    results = search_engine.search(
        ISSUE,
        top_k=5,
    )

    for entity in results:

        print(
            f"{entity.type.value}: "
            f"{entity.qualified_name or entity.name}"
        )

    print("\nGenerating candidates...")

    candidates = generate_candidates(
        issue=ISSUE,
        entities=parsed_repository.entities,
        graph=graph,
    )

    print("\nRanking candidates...")

    ranked = rank_candidates(candidates)

    print("\nTop candidates:\n")

    for candidate in ranked[:10]:

        entity = candidate.entity

        print(
            f"{candidate.score:.3f} | "
            f"{entity.type.value} | "
            f"{entity.qualified_name or entity.name}"
        )

        print(
            f"  Evidence: "
            f"{', '.join(candidate.evidence)}"
        )


if __name__ == "__main__":
    main()