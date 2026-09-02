from graphmem.graph.networkx_store import NetworkXGraphStore
from graphmem.models.repository import ParsedRepository


class GraphBuilder:
    """
    Builds a repository graph from parsed repository data.
    """

    def build(
        self,
        repository: ParsedRepository,
    ) -> NetworkXGraphStore:

        graph = NetworkXGraphStore()

        # Add all nodes first.
        for entity in repository.entities:
            graph.add_entity(entity)

        # Add all relationships.
        for relation in repository.relations:
            graph.add_relation(relation)

        return graph