"""Run the legacy family derivation and render audits on fictional data."""

import os
import sys
import tempfile
from pathlib import Path

CODEBASE = Path(__file__).resolve().parents[1]
for path in (CODEBASE, CODEBASE / "App"):
    sys.path.insert(0, str(path))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mosaic-family-synthetic-") as temporary:
        root = Path(temporary) / "Mosaic - Synthetic Data"
        os.environ["PEOPLE_RELATIONSHIPS_BOOTSTRAP"] = str(Path(temporary) / "absent-bootstrap.json")
        from Tests.synthetic_mosaic import build

        build(root)
        os.environ["PEOPLE_RELATIONSHIPS_ROOT"] = str(root)
        from app.backend.domain.family import engine
        from app.backend.model import load_model, run_family_audits, validate_model

        engine.rebind_active_root()
        model = load_model(root / "Database" / "relationships.db")
        validate_model(model)
        audits = run_family_audits(model)
        mermaid = engine.build_mermaid(model)
        engine.audit_render_mapping(model, mermaid)
        print(f"Synthetic family audit PASS: {audits['people']} fictional people; {audits['derived_focus_cousin_paths']} derived focus paths")


if __name__ == "__main__":
    main()
