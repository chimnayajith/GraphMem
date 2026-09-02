from graphmem.models.entities import CodeEntity


class EntityIndex:
    """Exact and field-based index over CodeEntity objects."""

    def __init__(self, entities: list[CodeEntity]):
        self.entities = list(entities)

        self._by_name: dict[str, list[CodeEntity]] = {}
        self._by_qualified_name: dict[str, list[CodeEntity]] = {}
        self._by_path: dict[str, list[CodeEntity]] = {}

        self._build()

    def _build(self) -> None:
        for entity in self.entities:
            self._add(
                self._by_name,
                entity.name,
                entity,
            )

            self._add(
                self._by_qualified_name,
                entity.qualified_name,
                entity,
            )

            self._add(
                self._by_path,
                entity.path,
                entity,
            )

    @staticmethod
    def _add(
        index: dict[str, list[CodeEntity]],
        value: str | None,
        entity: CodeEntity,
    ) -> None:
        if not value:
            return

        key = value.lower()

        index.setdefault(key, []).append(entity)

    def search(self, query: str) -> list[CodeEntity]:
        """Return entities matching the query exactly."""

        query = query.strip().lower()

        if not query:
            return []

        results: dict[str, CodeEntity] = {}

        for entity in self._by_name.get(query, []):
            results[entity.id] = entity

        for entity in self._by_qualified_name.get(query, []):
            results[entity.id] = entity

        for entity in self._by_path.get(query, []):
            results[entity.id] = entity

        return list(results.values())