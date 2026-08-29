from collections import deque
from dataclasses import dataclass

from graphmem.graph.store import GraphStore
from graphmem.models.entities import CodeEntity


@dataclass
class TraversalResult:
    entity: CodeEntity
    depth: int
    path: list[str]


def expand_from_seed(
    graph: GraphStore,
    seed: CodeEntity,
    max_depth: int = 2,
) -> list[TraversalResult]:
    """
    Traverse the repository graph starting from one seed entity.

    Args:
        graph: GraphStore implementation.
        seed: Entity from which traversal starts.
        max_depth: Maximum number of graph hops.

    Returns:
        Entities discovered during traversal, along with
        their graph depth and traversal path.
    """

    results = []

    visited = {seed.id}

    queue = deque([
    (seed, 0, [seed.id])
    ])

    while queue:
        entity, depth, path = queue.popleft()

        results.append(
            TraversalResult(
                entity=entity,
                depth=depth,
                path=path,
            )
        )

        # Stop expanding once max depth is reached.
        if depth >= max_depth:
            continue

        for neighbor in graph.neighbors(entity.id):

            if neighbor.id in visited:
                continue

            visited.add(neighbor.id)

            queue.append(
                (
                    neighbor,
                    depth + 1,
                    path + [neighbor.id],
                )
            )

    return results
