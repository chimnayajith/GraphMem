from graphmem.parsing.python_parser import PythonParser


def main():
    parser = PythonParser()

    parsed = parser.parse_repository(
        "examples/sample_repo"
    )

    print("\n=== PARSER RESULTS ===\n")

    print(f"Entities: {len(parsed.entities)}")
    print(f"Relations: {len(parsed.relations)}")

    print("\n=== ENTITIES ===\n")

    for entity in parsed.entities:
        print(
            f"[{entity.type.value}] "
            f"{entity.name}"
        )

        print(f"  ID: {entity.id}")
        print(f"  Path: {entity.path}")
        print(f"  Parent: {entity.parent_id}")

        if entity.qualified_name:
            print(
                f"  Qualified: "
                f"{entity.qualified_name}"
            )

        if entity.metadata:
            print(
                f"  Metadata: "
                f"{entity.metadata}"
            )

    print("\n=== RELATIONS ===\n")

    for relation in parsed.relations:
        print(
            f"{relation.source_id}"
        )
        print(
            f"  --[{relation.type.value}]-->"
        )
        print(
            f"{relation.target_id}\n"
        )


if __name__ == "__main__":
    main()