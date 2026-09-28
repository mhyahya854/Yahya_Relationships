"""Load and certify the synthetic Connections redesign family facts.

This is intentionally separate from ``phase10_synthetic_fixture.py``.  The
older fixture certifies a different, name-specific kinship matrix; this one
certifies the route shapes and relationship kinds used by the Connections
redesign screenshots without weakening the older coverage.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.backend.domain.family import engine
from app.backend.domain.relationships import path_service
from app.backend.model import load_model, validate_model
from app.backend.services import relationship

from phase10_synthetic_fixture import REQUIRED_PARENT_KINDS, _generation_count, _insert_facts


def main() -> None:
    db_path = Path(sys.argv[1]).resolve()
    fixture = json.load(sys.stdin)
    _insert_facts(db_path, fixture)

    model = load_model(db_path)
    validate_model(model)
    mermaid = engine.build_mermaid(model)
    engine.audit_render_mapping(model, mermaid)

    source_id = fixture["multipath"]["from"]
    target_id = fixture["multipath"]["to"]
    paths = path_service.get_relationship_paths(
        source_id,
        target_id,
        max_depth=15,
        max_paths=50,
    )["paths"]
    relationship_result = relationship.get_relationship(source_id, target_id)
    entries = relationship_result["primary"] + relationship_result["additional"]
    parent_kinds = {fact["kind"] for fact in model["parent_child"]}

    assert len(model["people"]) == fixture["expected_people"]
    assert _generation_count(model) >= 5
    assert len(model["marriages"]) >= 12
    assert len(model["sibling_groups"]) >= 6
    assert REQUIRED_PARENT_KINDS <= parent_kinds
    assert len(paths) >= 2
    assert {"maternal", "paternal"} <= {path.get("side") for path in paths}
    assert entries
    assert all(entry.get("path_ids") for entry in entries)

    print(json.dumps({
        "people": len(model["people"]),
        "generations": _generation_count(model),
        "parent_child": len(model["parent_child"]),
        "parent_kinds": sorted(parent_kinds),
        "marriages": len(model["marriages"]),
        "sibling_groups": len(model["sibling_groups"]),
        "multipath_paths": len(paths),
        "multipath_sides": sorted(side for side in {path.get("side") for path in paths} if side),
        "relationship_semantics": sorted({entry["semantic_id"] for entry in entries}),
        "mermaid_bytes": len(mermaid.encode("utf-8")),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
