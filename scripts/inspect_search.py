from graphmem.parsing.python_parser import PythonParser
from graphmem.retrieval.search import SearchEngine


REPOSITORY_PATH = "examples/sample_repo"


def main():

    print("\n=== PARSING REPOSITORY ===\n")

    parser = PythonParser()

    parsed = parser.parse_repository(
        REPOSITORY_PATH
    )

    print(
        f"Indexed entities: {len(parsed.entities)}"
    )

    print("\n=== SEARCH TESTS ===\n")

    search_engine = SearchEngine(
        parsed.entities
    )

    queries = [
        "normalize",
        "formatter",
        "base",
        "function",
    ]

    for query in queries:

        print(f"\nQuery: {query}")

        results = search_engine.search(
            query,
            top_k=5,
        )

        if not results:
            print("  No results")

        for entity in results:

            print(
                f"  [{entity.type.value}] "
                f"{entity.qualified_name or entity.name}"
            )

            print(f"    Path: {entity.path}")


if __name__ == "__main__":
    main()