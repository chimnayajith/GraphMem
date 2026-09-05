from graphmem.parsing.python_parser import PythonParser
from graphmem.graph.builder import GraphBuilder


def main():
    print("\n=== PARSING REPOSITORY ===\n")

    parser = PythonParser()

    parsed = parser.parse_repository(
        "examples/sample_repo"
    )

    print(
        f"Entities parsed: {len(parsed.entities)}"
    )

    print(
        f"Relations parsed: {len(parsed.relations)}"
    )

    print("\n=== BUILDING GRAPH ===\n")

    graph = GraphBuilder().build(parsed)

    print("Graph built successfully.")

    print("\n=== GRAPH NEIGHBORS ===\n")

    for entity in parsed.entities:

        neighbors = graph.neighbors(entity.id)

        if not neighbors:
            continue

        print(
            f"{entity.type.value}: {entity.name}"
        )

        for neighbor in neighbors:

            print(
                f"  → {neighbor.type.value}: "
                f"{neighbor.name}"
            )

        print()


if __name__ == "__main__":
    main()