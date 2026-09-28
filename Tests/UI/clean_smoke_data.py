"""Remove people/journal/backup artifacts created by Tests/UI/smoke.mjs.

Run from the repository root:
    PEOPLE_RELATIONSHIPS_ROOT=<explicit-test-root> python Tests/UI/clean_smoke_data.py
"""

import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

if not os.environ.get("PEOPLE_RELATIONSHIPS_ROOT"):
    raise SystemExit("PEOPLE_RELATIONSHIPS_ROOT must explicitly name an isolated test Data Root.")
if os.environ.get("MOSAIC_ISOLATED_TEST_ROOT") != "1":
    raise SystemExit("MOSAIC_ISOLATED_TEST_ROOT=1 is required before cleanup.")

ROOT = Path(os.environ["PEOPLE_RELATIONSHIPS_ROOT"]).resolve()
TEMP_ROOT = Path(tempfile.gettempdir()).resolve()
ALLOWED_TEST_PREFIXES = ("smoke_e2e_root_", "phase10-smoke-")
try:
    ROOT.relative_to(TEMP_ROOT)
except ValueError:
    raise SystemExit("Refusing cleanup outside the system temporary directory.")
if not ROOT.name.startswith(ALLOWED_TEST_PREFIXES):
    raise SystemExit("Refusing cleanup for an unrecognized isolated test root.")

database_candidates = (
    ROOT / "Database" / "relationships.db",
    ROOT / "Database" / "Main" / "family.db",
)
database = next((candidate for candidate in database_candidates if candidate.is_file()), None)
if database is None:
    print("cleaned smoke-test artifacts for no supported test database")
    raise SystemExit(0)

con = sqlite3.connect(database)
ids = [
    row[0]
    for row in con.execute("SELECT id FROM people WHERE name LIKE 'Sami Friend%'")
]
for person_id in ids:
    con.execute(
        'DELETE FROM fact_sources WHERE entity_type="people" AND entity_key=?',
        (person_id,),
    )
    con.execute(
        "DELETE FROM general_relationships WHERE person_a=? OR person_b=?",
        (person_id, person_id),
    )
    con.execute("DELETE FROM aliases WHERE person_id=?", (person_id,))
    con.execute("DELETE FROM person_groups WHERE person_id=?", (person_id,))
    con.execute("DELETE FROM people WHERE id=?", (person_id,))
import time

def safe_rmtree(path: Path):
    for attempt in range(5):
        try:
            shutil.rmtree(path)
            return
        except Exception:
            time.sleep(0.5)
    shutil.rmtree(path, ignore_errors=True)

con.commit()
con.close()
for person_id in ids:
    for people_dir in (ROOT / "People", ROOT / "Database" / "People"):
        if not people_dir.is_dir():
            continue
        for folder in people_dir.rglob(person_id):
            if folder.is_dir():
                safe_rmtree(folder)
state = ROOT / "Database" / "Config" / "state.json"
if state.exists():
    state.unlink()
history = ROOT / "Database" / "Config" / "restore-history.json"
if history.exists():
    history.unlink()
manifests = [m for m in (ROOT / "Backups").rglob("manifest.json") if m.is_file()]
to_delete = []
for manifest in manifests:
    backup = manifest.parent
    if not backup.is_dir() or "Safety" in str(backup):
        continue
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        continue
    label = payload.get("label", "")
    paths = [entry.get("path", "") for entry in payload.get("files", [])]
    if (
        any(person_id in path for person_id in ids for path in paths)
        or label in ("verified-snapshot", "test-verification")
        or "pre-restore" in backup.name
        or "verified-snapshot" in backup.name
        or "test-verification" in backup.name
    ):
        to_delete.append(backup)

for backup in to_delete:
    if backup.is_dir():
        safe_rmtree(backup)
print("cleaned smoke-test artifacts for", ids or "no test people")
