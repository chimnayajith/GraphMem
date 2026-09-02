from rank_bm25 import BM25Okapi

from graphmem.models.entities import CodeEntity


class BM25Index:
    """BM25 lexical index over CodeEntity objects."""

    def __init__(self, entities: list[CodeEntity]):
        self.entities = list(entities)

        self._documents = [
            self._build_document(entity)
            for entity in self.entities
        ]

        self._tokenized_documents = [
            document.lower().split()
            for document in self._documents
        ]

        self._bm25 = BM25Okapi(self._tokenized_documents)

    @staticmethod
    def _build_document(entity: CodeEntity) -> str:
        return " ".join(
            [
                entity.name or "",
                entity.qualified_name or "",
                entity.path or "",
                entity.type.value,
            ]
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[CodeEntity]:
        """Return the top BM25-ranked entities for a query."""

        query = query.strip()

        if not query:
            return []

        query_tokens = query.lower().split()

        scores = self._bm25.get_scores(query_tokens)

        ranked_indices = sorted(
            range(len(self.entities)),
            key=lambda index: scores[index],
            reverse=True,
        )

        return [
            self.entities[index]
            for index in ranked_indices[:top_k]
            if scores[index] > 0
        ]