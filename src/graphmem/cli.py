import argparse

from graphmem.ingestion.pipeline import RepositoryIngestor


def main():
    parser = argparse.ArgumentParser(
        description="GraphMem repository intelligence"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser(
        "index",
        help="Parse and index a repository",
    )

    index_parser.add_argument(
        "repository",
        help="Path to the repository",
    )

    args = parser.parse_args()

    if args.command == "index":
        ingestor = RepositoryIngestor()
        result = ingestor.ingest(args.repository)

        print(f"Repository: {result.repository_path}")
        print(f"Entities:   {len(result.parsed.entities)}")
        print(f"Relations:  {len(result.parsed.relations)}")
        print(f"Graph nodes: {result.graph.entity_count()}")
        print(f"Graph edges: {result.graph.relation_count()}")

        languages = {
            entity.metadata.get("language")
            for entity in result.parsed.entities
            if entity.metadata.get("language")
        }

        print(f"Languages:  {', '.join(sorted(languages))}")


if __name__ == "__main__":
    main()