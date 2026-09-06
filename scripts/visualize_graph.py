from pathlib import Path
import sys

from pyvis.network import Network

from graphmem.ingestion.pipeline import RepositoryIngestor


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/visualize_graph.py <repository>")
        sys.exit(1)

    repository_path = sys.argv[1]

    print(f"Indexing repository: {repository_path}")

    ingestor = RepositoryIngestor()
    result = ingestor.ingest(repository_path)

    graph = result.graph.graph

    net = Network(
        height="800px",
        width="100%",
        directed=True,
        bgcolor="#111111",
        font_color="white",
    )

    # Add nodes without the CodeEntity object.
    for node_id, data in graph.nodes(data=True):
        entity = data["entity"]

        label = entity.name or entity.id

        title = (
            f"<b>Type:</b> {entity.type.value}<br>"
            f"<b>Name:</b> {entity.name}<br>"
            f"<b>Path:</b> {entity.path or '-'}<br>"
            f"<b>Lines:</b> "
            f"{entity.start_line or '-'} - {entity.end_line or '-'}"
        )

        net.add_node(
            node_id,
            label=label,
            title=title,
        )

    # Add edges using only JSON-safe values.
    for source, target, edge_data in graph.edges(data=True):
        relation_type = edge_data.get("relation_type")

        if hasattr(relation_type, "value"):
            relation_type = relation_type.value

        net.add_edge(
            source,
            target,
            label=str(relation_type or ""),
        )

    # Improve physics/layout.
    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "stabilization": {
          "iterations": 200
        }
      },
      "interaction": {
        "hover": true,
        "navigationButtons": true,
        "keyboard": true
      },
      "edges": {
        "arrows": {
          "to": {
            "enabled": true
          }
        },
        "smooth": true
      }
    }
    """)

    output = Path("graphmem_graph.html")
    net.write_html(str(output))

    print()
    print("Graph generated!")
    print(f"Entities:    {result.graph.entity_count()}")
    print(f"Relations:   {result.graph.relation_count()}")
    print(f"Output:      {output.resolve()}")


if __name__ == "__main__":
    main()