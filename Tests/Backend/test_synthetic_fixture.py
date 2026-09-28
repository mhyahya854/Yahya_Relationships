"""Contract checks for the canonical fictional Data Root used by public tests."""

import sqlite3


def test_canonical_fixture_has_directional_relationship_and_raw_duplicates(isolated):
    with sqlite3.connect(isolated / "Database" / "relationships.db") as connection:
        darya_id = connection.execute("SELECT id FROM people WHERE name='Darya Sol'").fetchone()[0]
        quinn_id = connection.execute("SELECT id FROM people WHERE name='Quinn Aster'").fetchone()[0]
        mentor = connection.execute(
            "SELECT person_a,person_b,direction_from FROM general_relationships "
            "WHERE type='mentor' AND directionality='directional'"
        ).fetchone()
        assert mentor == (*sorted((darya_id, quinn_id)), darya_id)
        assert connection.execute(
            "SELECT COUNT(*) FROM general_relationships WHERE type='friend' AND directionality='symmetric'"
        ).fetchone()[0] == 1
    first = isolated / "Raw" / "synthetic-note.txt"
    second = isolated / "Raw" / "synthetic-note-copy.txt"
    assert first.is_file() and second.is_file()
    assert first.read_bytes() == second.read_bytes()
    with sqlite3.connect(isolated / "Database" / "relationships.db") as connection:
        rows = connection.execute(
            "SELECT id,current_relative_path,sha256 FROM raw_items WHERE current_relative_path IN (?,?)",
            ("Raw/synthetic-note.txt", "Raw/synthetic-note-copy.txt"),
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] != rows[1][0] and rows[0][2] and rows[0][2] == rows[1][2]
        assert connection.execute(
            "SELECT COUNT(*) FROM raw_item_paths WHERE raw_item_id IN (?,?) AND path_event='DISCOVERED'",
            (rows[0][0], rows[1][0]),
        ).fetchone()[0] == 2
        groups = connection.execute(
            "SELECT duplicate_group_id FROM raw_duplicate_members WHERE raw_item_id IN (?,?)",
            (rows[0][0], rows[1][0]),
        ).fetchall()
        assert len(groups) == 2 and groups[0][0] == groups[1][0]
