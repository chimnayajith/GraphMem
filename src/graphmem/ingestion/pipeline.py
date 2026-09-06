from dataclasses import dataclass

from graphmem.graph.builder import GraphBuilder
from graphmem.graph.networkx_store import NetworkXGraphStore
from graphmem.retrieval.search import SearchEngine
from graphmem.models.repository import ParsedRepository
from graphmem.ingestion.scanner import RepositoryScanner


@dataclass
class RepositoryIndex:
    repository_path: str
    parsed: ParsedRepository
    graph: NetworkXGraphStore
    search: SearchEngine


class RepositoryIngestor:
    """End-to-end repository ingestion pipeline."""

    def ingest(self, repository_path: str) -> RepositoryIndex:
        scanner = RepositoryScanner(repository_path)

        parsed = scanner.parse()

        builder = GraphBuilder()
        graph = builder.build(parsed)

        search = SearchEngine(parsed.entities)

        return RepositoryIndex(
            repository_path=str(scanner.repository_path),
            parsed=parsed,
            graph=graph,
            search=search,
        )