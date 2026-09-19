"""CLI runner for Mosaic Phase 11 Canonical Migration.

Usage:
  python Codebase/Scripts/migrate_canonical.py --dry-run
  python Codebase/Scripts/migrate_canonical.py --execute
  python Codebase/Scripts/migrate_canonical.py --verify
"""

import argparse
import json
import sys
from pathlib import Path

# Bootstrap backend imports
codebase_app = Path(__file__).resolve().parents[1] / "App"
if str(codebase_app) not in sys.path:
    sys.path.insert(0, str(codebase_app))

from app.backend.data_root.manager import DataRootManager
from app.backend.domain.migration.engine import (
    detect_migration_status,
    execute_migration,
    plan_migration,
)
from app.backend.data_root.validation import audit_data_root


def main() -> None:
    parser = argparse.ArgumentParser(description="Mosaic Phase 11 Canonical Data Foundation Migration")
    parser.add_argument("--root", help="Explicit target Data Root directory")
    parser.add_argument("--dry-run", action="store_true", help="Report planned migration without mutating data")
    parser.add_argument("--execute", action="store_true", help="Execute safe atomic migration with pre-migration backup")
    parser.add_argument("--verify", action="store_true", help="Run deterministic data integrity audit")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    args = parser.parse_args()
    target_root = Path(args.root).resolve() if args.root else DataRootManager.resolve_active_root()

    if args.verify:
        health = audit_data_root(target_root)
        result = health.to_dict()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Data Root Health: {'OK' if health.ok else 'ISSUES DETECTED'}")
            print(f"  Layout: {health.layout_mode}")
            print(f"  Root: {health.root_path}")
            if health.database:
                print(f"  DB Schema: v{health.database.schema_version}, People: {health.database.people_count}")
            for issue in health.issues:
                print(f"  [{issue.severity.upper()}] {issue.code}: {issue.message}")
        sys.exit(0 if health.ok else 1)

    if args.execute:
        print(f"Executing Phase 11 canonical migration on: {target_root}")
        res = execute_migration(target_root, dry_run=False)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print("Migration SUCCESS!")
            print(f"  Safety backup created: {res.get('safety_backup_id')}")
            print(f"  Target database: {res.get('target_db_path')}")
            print(f"  Migrated people: {res.get('migrated_people_count')}")
        sys.exit(0)

    # Default to dry-run
    plan = plan_migration(target_root)
    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        print("=== Mosaic Phase 11 Migration Plan (DRY-RUN) ===")
        print(f"  Can migrate: {plan.get('can_migrate')}")
        print(f"  Already migrated: {plan.get('already_migrated', False)}")
        print(f"  Source DB: {plan.get('source_db_path')}")
        print(f"  Target DB: {plan.get('target_db_path')}")
        print(f"  Source schema: v{plan.get('source_schema_version')} -> Target schema: v{plan.get('target_schema_version')}")
        print(f"  People count: {plan.get('people_count')}")
        print("\nProposed ID Mappings:")
        for m in plan.get("mappings", []):
            print(f"  {m['old_id']} -> {m['canonical_id']} ({m['category']})")
        if plan.get("warnings"):
            print("\nWarnings:")
            for w in plan["warnings"]:
                print(f"  - {w}")
        if plan.get("conflicts"):
            print("\nConflicts:")
            for c in plan["conflicts"]:
                print(f"  - {c}")


if __name__ == "__main__":
    main()
