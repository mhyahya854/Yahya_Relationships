"""Remove people/journal/backup artifacts created by Codebase/Tests/UI/smoke.mjs.

Run from the repository root:
    python Codebase/Tests/UI/clean_smoke_data.py
"""

import json
import os
import shutil
import sqlite3
from pathlib import Path

ROOT = (
    Path(os.environ["PEOPLE_RELATIONSHIPS_ROOT"]).resolve()
    if os.environ.get("PEOPLE_RELATIONSHIPS_ROOT")
    else Path(__file__).resolve().parents[3]
)
con = sqlite3.connect(ROOT / "Database" / "Main" / "family.db")
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
    for folder in (ROOT / "Database" / "People").rglob(person_id):
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
