from graphmem.indexing.bm25_index import BM25Index
from graphmem.indexing.entity_index import EntityIndex
from graphmem.models.entities import CodeEntity


class SearchEngine:
    """Search repository entities using exact matching and BM25."""

    def __init__(self, entities: list[CodeEntity]):
        self.entities = list(entities)

        self.entity_index = EntityIndex(self.entities)
        self.bm25_index = BM25Index(self.entities)

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[CodeEntity]:
        """Return combined exact-match and BM25 search results."""

        if not query.strip():
            return []

        results: dict[str, CodeEntity] = {}

        # Exact entity/path matches get priority.
        for entity in self.entity_index.search(query):
            results[entity.id] = entity

        # Add BM25 results without duplicating exact matches.
        for entity in self.bm25_index.search(query, top_k=top_k):
            results[entity.id] = entity

        return list(results.values())[:top_k]