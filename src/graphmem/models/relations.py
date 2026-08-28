from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RelationType(str, Enum):
    # Repository structure
    CONTAINS = "contains"

    # Code relationships
    IMPORTS = "imports"
    CALLS = "calls"
    INHERITS = "inherits"
    REFERENCES = "references"

    # Fine-grained relationships
    DEFINES = "defines"
    USES = "uses"
    DATAFLOW_DEF_USE = "dataflow_def_use"

    # Future repository intelligence
    MENTIONS = "mentions"
    CHANGES = "changes"
    FIXES = "fixes"


@dataclass
class Relation:
    source_id: str
    target_id: str
    type: RelationType

    metadata: dict[str, Any] = field(default_factory=dict)