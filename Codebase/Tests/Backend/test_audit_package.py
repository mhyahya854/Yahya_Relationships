"""Tests for package content privacy and security auditor.

Verifies that the audit strictly catches any private family databases, journals,
backups, or development artifacts in staged distributions, while allowing
legitimate compiled application assets.
"""

import zipfile
from pathlib import Path
import sys

# Import audit_package tool
ROOT = Path(__file__).resolve().parents[2]
PACKAGING_SCRIPTS = ROOT / "Packaging" / "Scripts"
if str(PACKAGING_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PACKAGING_SCRIPTS))

import audit_package


def test_audit_allows_legitimate_application_tree(tmp_path: Path):
    """Verifies that normal staged desktop application files pass cleanly."""
    bundle = tmp_path / "staged_bundle"
    bundle.mkdir()

    # Create typical clean application assets
    (bundle / "people-relationships.exe").write_bytes(b"MZfakebinarycontent12345")
    (bundle / "index.html").write_text("<!DOCTYPE html><html><body>App</body></html>")

    assets = bundle / "assets"
    assets.mkdir()
    (assets / "index-abc123.js").write_text("console.log('People Relationships frontend');")
    (assets / "style-def456.css").write_text("body { background: #000; }")
    (assets / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")

    binaries = bundle / "binaries"
    binaries.mkdir()
    (binaries / "people-relationships-backend.exe").write_bytes(b"fakebackendbinary")

    ok, violations = audit_package.audit_directory(bundle)
    assert ok is True
    assert len(violations) == 0


def test_audit_catches_staged_fake_family_db(tmp_path: Path):
    """Verifies that any staged family.db is caught immediately."""
    bundle = tmp_path / "bundle_with_db"
    bundle.mkdir()
    (bundle / "family.db").write_bytes(b"dummy SQLite format 3\x00 fake content")

    ok, violations = audit_package.audit_directory(bundle)
    assert ok is False
    assert any("family.db" in v[0].lower() for v in violations)


def test_audit_catches_staged_fake_journal_md(tmp_path: Path):
    """Verifies that any staged journal.md is caught immediately."""
    bundle = tmp_path / "bundle_with_journal"
    bundle.mkdir()
    subfolder = bundle / "notes"
    subfolder.mkdir()
    (subfolder / "journal.md").write_text("# Personal Journal Entry\nSynthetic text")

    ok, violations = audit_package.audit_directory(bundle)
    assert ok is False
    assert any("journal.md" in v[0].lower() for v in violations)


def test_audit_catches_staged_fake_backups_directory(tmp_path: Path):
    """Verifies that any staged Backups/ folder is caught."""
    bundle = tmp_path / "bundle_with_backups"
    bundle.mkdir()
    backups = bundle / "Backups"
    backups.mkdir()
    (backups / "archive_2026.zip").write_bytes(b"PKfakearchive")

    ok, violations = audit_package.audit_directory(bundle)
    assert ok is False
    assert any("backups" in v[0].lower() for v in violations)


def test_audit_catches_staged_fake_database_people(tmp_path: Path):
    """Verifies that any staged Database/People folder is caught."""
    bundle = tmp_path / "bundle_with_people"
    bundle.mkdir()
    people_dir = bundle / "Database" / "People" / "Family" / "Person_A"
    people_dir.mkdir(parents=True)
    (people_dir / "profile.json").write_text('{"name": "Test Person"}')

    ok, violations = audit_package.audit_directory(bundle)
    assert ok is False
    assert any("database/people" in v[0].lower() for v in violations)


def test_audit_catches_violation_in_zip_archive(tmp_path: Path):
    """Verifies that an archive containing forbidden data fails audit."""
    zip_file = tmp_path / "test_package.zip"
    with zipfile.ZipFile(zip_file, "w") as zf:
        zf.writestr("index.html", "<html></html>")
        zf.writestr("data/family.db", "synthetic content")

    ok, violations = audit_package.audit_archive(zip_file)
    assert ok is False
    assert any("family.db" in v[0].lower() for v in violations)


def test_audit_binary_detects_embedded_sqlite_header(tmp_path: Path):
    """Verifies that raw binary scan catches intact embedded SQLite database header."""
    fake_exe = tmp_path / "installer.exe"
    # Construct binary containing b"SQLite format 3\x00"
    content = b"MZ" + b"\x00" * 500 + b"SQLite format 3\x00" + b"\x00" * 200
    fake_exe.write_bytes(content)

    ok, violations = audit_package.audit_binary_heuristics(fake_exe)
    assert ok is False
    assert len(violations) > 0
