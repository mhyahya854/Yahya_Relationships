"""Remove people/journal/backup artifacts created by tests/ui/smoke.mjs.

Run from the repository root:
    python tests/ui/clean_smoke_data.py
"""

import json
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
con = sqlite3.connect(ROOT / "family.db")
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
con.commit()
con.close()
for person_id in ids:
    for folder in (ROOT / "people").rglob(person_id):
        if folder.is_dir():
            shutil.rmtree(folder)
state = ROOT / "config" / "state.json"
if state.exists():
    state.unlink()
for backup in (ROOT / "backups").iterdir():
    if not backup.is_dir():
        continue
    manifest = backup / "manifest.json"
    if not manifest.exists():
        continue
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        continue
    paths = [entry.get("path", "") for entry in payload.get("files", [])]
    if any(person_id in path for person_id in ids for path in paths):
        shutil.rmtree(backup)
print("cleaned smoke-test artifacts for", ids or "no test people")
