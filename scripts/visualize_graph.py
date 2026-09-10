from pathlib import Path
import sys
import html

from pyvis.network import Network

from graphmem.ingestion.pipeline import RepositoryIngestor


# ============================================================
# Node appearance
# ============================================================

NODE_COLORS = {
    "repository": "#FFD166",
    "directory": "#06D6A0",
    "file": "#118AB2",
    "class": "#9B5DE5",
    "function": "#F15BB5",
    "method": "#F15BB5",
    "statement": "#EF476F",
}

NODE_SHAPES = {
    "repository": "diamond",
    "directory": "box",
    "file": "box",
    "class": "ellipse",
    "function": "dot",
    "method": "dot",
    "statement": "square",
}


# ============================================================
# Edge appearance
# ============================================================

EDGE_COLORS = {
    "contains": "#8ECAE6",
    "imports": "#219EBC",
    "calls": "#FB8500",
    "inherits": "#9B5DE5",
    "references": "#FFB703",
    "defines": "#90BE6D",
    "uses": "#F8961E",
    "dataflow_def_use": "#E63946",

    # Future repository-intelligence relations
    "mentions": "#A8DADC",
    "changes": "#457B9D",
    "fixes": "#2A9D8F",
}


def enum_value(value):
    """
    Convert Enum values into strings.

    Works for:
        EntityType.CLASS
        RelationType.CALLS
        "class"
        "calls"
    """

    if hasattr(value, "value"):
        return value.value

    return str(value)


def safe(value, default="-"):
    """HTML-escape values before putting them in tooltips."""

    if value is None or value == "":
        return default

    return html.escape(str(value))


def format_lines(entity):
    """Format source line information."""

    start = entity.start_line
    end = entity.end_line

    if start is None and end is None:
        return "-"

    if start == end or end is None:
        return str(start or end)

    return f"{start} - {end}"


def build_node_label(entity):
    """
    Label shown directly on the graph.

    Prefer:
        qualified_name

    then:
        name

    then:
        filename
    """

    if entity.qualified_name:
        return entity.qualified_name

    if entity.name:
        return entity.name

    if entity.path:
        return Path(entity.path).name

    return entity.id


def build_node_title(entity):
    """
    Build a readable tooltip for a graph node.

    PyVis/vis-network renders this as plain text, so don't
    put HTML tags in here.
    """

    entity_type = enum_value(entity.type)

    lines = [
        f"Name: {entity.name or '-'}",
        f"Type: {entity_type}",
        f"ID: {entity.id or '-'}",
        f"Qualified Name: {entity.qualified_name or '-'}",
        f"Path: {entity.path or '-'}",
        f"Lines: {format_lines(entity)}",
        f"Parent ID: {entity.parent_id or '-'}",
    ]

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    if entity.metadata:
        lines.append("")
        lines.append("Metadata:")

        for key, value in entity.metadata.items():
            lines.append(f"  {key}: {value}")

    return "\n".join(lines)


def build_edge_title(source_entity, target_entity, relation_type):
    """
    Build a readable plain-text tooltip for an edge.
    """

    relation_name = relation_type.replace("_", " ").title()

    return (
        f"Relation: {relation_name}\n"
        f"Source: {source_entity.name or '-'}\n"
        f"Target: {target_entity.name or '-'}"
    )

def main():

    # ========================================================
    # Arguments
    # ========================================================

    if len(sys.argv) != 2:
        print(
            "Usage: python scripts/visualize_graph.py <repository>"
        )
        sys.exit(1)

    repository_path = sys.argv[1]

    print(f"Indexing repository: {repository_path}")

    # ========================================================
    # Build repository graph
    # ========================================================

    ingestor = RepositoryIngestor()

    result = ingestor.ingest(repository_path)

    graph = result.graph.graph

    # ========================================================
    # PyVis
    # ========================================================

    net = Network(
        height="100vh",
        width="100%",
        directed=True,
        bgcolor="#111827",
        font_color="#F9FAFB",
        notebook=False,
    )

    # ========================================================
    # Nodes
    # ========================================================

    node_type_counts = {}

    for node_id, data in graph.nodes(data=True):

        entity = data["entity"]

        entity_type = enum_value(entity.type)

        color = NODE_COLORS.get(
            entity_type,
            "#ADB5BD",
        )

        shape = NODE_SHAPES.get(
            entity_type,
            "dot",
        )

        label = build_node_label(entity)

        title = build_node_title(entity)

        node_type_counts[entity_type] = (
            node_type_counts.get(entity_type, 0) + 1
        )

        net.add_node(
            node_id,

            label=label,

            title=title,

            shape=shape,

            size=20,

            color={
                "background": color,
                "border": "#FFFFFF",

                "highlight": {
                    "background": color,
                    "border": "#FFFFFF",
                },

                "hover": {
                    "background": color,
                    "border": "#FFFFFF",
                },
            },

            font={
                "color": "#FFFFFF",
                "size": 14,
                "face": "Arial",
            },

            borderWidth=1,
            borderWidthSelected=3,
        )

    # ========================================================
    # Edges
    # ========================================================

    for source, target, edge_data in graph.edges(data=True):

        relation_type = enum_value(
            edge_data.get("relation_type")
        )

        edge_color = EDGE_COLORS.get(
            relation_type,
            "#777777",
        )

        source_entity = graph.nodes[source]["entity"]
        target_entity = graph.nodes[target]["entity"]

        edge_title = build_edge_title(
            source_entity,
            target_entity,
            relation_type,
        )

        net.add_edge(
            source,
            target,

            label=relation_type.replace("_", " "),

            title=build_edge_title(
                source_entity,
                target_entity,
                relation_type,
            ),

            color={
                "color": edge_color,
                "highlight": "#FFFFFF",
                "hover": "#FFFFFF",
            },

            width=1.5,

            arrows={
                "to": {
                    "enabled": True,
                    "scaleFactor": 0.7,
                }
            },

            font={
                "color": "#D1D5DB",
                "size": 11,
                "strokeWidth": 3,
                "strokeColor": "#111827",
            },

            smooth={
                "enabled": True,
                "type": "dynamic",
            },
        )

    # ========================================================
    # Physics
    # ========================================================

    net.set_options("""
    {
      "physics": {
        "enabled": true,

        "solver": "forceAtlas2Based",

        "forceAtlas2Based": {
          "gravitationalConstant": -80,
          "centralGravity": 0.01,
          "springLength": 160,
          "springConstant": 0.08,
          "damping": 0.4,
          "avoidOverlap": 1
        },

        "stabilization": {
          "enabled": true,
          "iterations": 300,
          "updateInterval": 25
        }
      },

      "interaction": {
        "hover": true,
        "tooltipDelay": 100,

        "navigationButtons": true,

        "keyboard": {
          "enabled": true
        },

        "dragNodes": true,
        "dragView": true,
        "zoomView": true
      },

      "edges": {
        "selectionWidth": 3,

        "smooth": {
          "enabled": true,
          "type": "dynamic"
        },

        "arrows": {
          "to": {
            "enabled": true,
            "scaleFactor": 0.7
          }
        }
      }
    }
    """)

    # ========================================================
    # Legend
    # ========================================================

    legend_items = []

    for entity_type, count in sorted(
        node_type_counts.items()
    ):

        color = NODE_COLORS.get(
            entity_type,
            "#ADB5BD",
        )

        display_name = (
            entity_type
            .replace("_", " ")
            .title()
        )

        legend_items.append(
            f"""
            <div style="
                display:flex;
                align-items:center;
                margin:6px 0;
            ">

                <span style="
                    display:inline-block;

                    width:14px;
                    height:14px;

                    background:{color};

                    margin-right:8px;

                    border:1px solid white;
                "></span>

                <span>
                    {display_name} ({count})
                </span>

            </div>
            """
        )

    legend_html = f"""
    <div style="
        position: fixed;

        top: 20px;
        right: 20px;

        background: rgba(17, 24, 39, 0.96);
        color: #F9FAFB;

        padding: 16px 20px;

        border-radius: 10px;

        font-family: Arial, sans-serif;
        font-size: 13px;

        border: 1px solid #374151;

        box-shadow: 0 4px 15px rgba(0,0,0,0.4);

        z-index: 9999;
    ">

        <div style="
            font-size:17px;
            font-weight:bold;

            margin-bottom:10px;
        ">
            Repository Graph
        </div>

        {''.join(legend_items)}

    </div>
    """

    # ========================================================
    # Write HTML
    # ========================================================

    output = Path("graphmem_graph.html")

    net.write_html(str(output))

    html_content = output.read_text()

    html_content = html_content.replace(
        "<body>",
        f"<body>{legend_html}",
    )

    output.write_text(html_content)

    # ========================================================
    # Summary
    # ========================================================

    print()
    print("Graph generated!")
    print(f"Entities:    {result.graph.entity_count()}")
    print(f"Relations:   {result.graph.relation_count()}")
    print(f"Output:      {output.resolve()}")

    print()
    print("Node types:")

    for entity_type, count in sorted(
        node_type_counts.items()
    ):
        print(
            f"  {entity_type:<15} {count}"
        )


if __name__ == "__main__":
    main()