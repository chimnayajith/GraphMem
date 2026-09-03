"""Quick manual demo of the Python parser.

    python examples/run_demo.py [path/to/repo]

Defaults to examples/sample_repo. Prints the entity/relation counts and
the CONTAINS tree so you can eyeball that it matches what's on disk.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from graphmem.models.entities import EntityType  # noqa: E402
from graphmem.models.relations import RelationType  # noqa: E402
from graphmem.parsing import PythonParser  # noqa: E402


def children_of(parsed, entity_id: str):
    child_ids = {
        r.target_id
        for r in parsed.relations
        if r.type == RelationType.CONTAINS and r.source_id == entity_id
    }
    return [e for e in parsed.entities if e.id in child_ids]


def print_tree(parsed, entity_id: str, indent: int = 0) -> None:
    entity = parsed.get_entity(entity_id)
    label = entity.qualified_name or entity.name or "(repo)"
    print("  " * indent + f"- [{entity.type.value}] {label}")
    for child in sorted(children_of(parsed, entity_id), key=lambda e: (e.type.value, e.name)):
        print_tree(parsed, child.id, indent + 1)


def main() -> None:
    repo_path = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "sample_repo")
    parsed = PythonParser().parse_repository(repo_path)

    print(f"Parsed: {parsed.repository_path}")
    print()

    counts: dict[str, int] = {}
    for e in parsed.entities:
        counts[e.type.value] = counts.get(e.type.value, 0) + 1
    for r in parsed.relations:
        key = f"relation:{r.type.value}"
        counts[key] = counts.get(key, 0) + 1
    for key, count in sorted(counts.items()):
        print(f"  {key:<28} {count}")
    print()

    print("CONTAINS tree:")
    repo_entity = next(e for e in parsed.entities if e.type == EntityType.REPOSITORY)
    print_tree(parsed, repo_entity.id)
    print()

    print("IMPORTS edges (repo-local only):")
    for rel in parsed.relations:
        if rel.type != RelationType.IMPORTS:
            continue
        src = parsed.get_entity(rel.source_id)
        dst = parsed.get_entity(rel.target_id)
        print(f"  {src.path}  ->  {dst.path}")


if __name__ == "__main__":
    main()
