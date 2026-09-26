"""Privacy gate behavior on a temporary public repository."""

import hashlib
import hmac
import importlib.util
import subprocess
from pathlib import Path

from privacy_gate import audit


def test_gate_rejects_private_roots_identity_paths_and_uncertified_images(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "Codebase").mkdir()
    (tmp_path / "Codebase" / "safe.py").write_text("print('fictional fixture')\n", encoding="utf-8")
    key = bytes.fromhex("11" * 32)
    signature = hmac.new(key, b"fictional person", hashlib.sha256).hexdigest()
    private_hash = hashlib.sha256(b"synthetic private baseline").hexdigest()
    hash_signature = hmac.new(key, private_hash.encode("ascii"), hashlib.sha256).hexdigest()
    subprocess.run(["git", "add", "Codebase/safe.py"], cwd=tmp_path, check=True)
    assert audit(tmp_path, key, {signature}) == []

    (tmp_path / "Codebase" / "private.py").write_text("owner = 'Fictional Person'\n", encoding="utf-8")
    (tmp_path / "Codebase" / "machine.py").write_text("path = 'C:/" + "Users/Somebody/private'\n", encoding="utf-8")
    escaped_path = "C:" + "\\" * 2 + "Users" + "\\" * 2 + "Somebody" + "\\" * 2 + "private"
    (tmp_path / "Codebase" / "escaped.py").write_text(f"path = '{escaped_path}'\n", encoding="utf-8")
    (tmp_path / "Codebase" / "hash.py").write_text(f"checksum = '{private_hash}'\n", encoding="utf-8")
    (tmp_path / "Database").mkdir()
    (tmp_path / "Database" / "relationships.db").write_bytes(b"SQLite format 3\0private")
    shots = tmp_path / "Documentation" / "UI-Screenshots" / "uncertified"
    shots.mkdir(parents=True)
    (shots / "sample.png").write_bytes(b"image placeholder")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    problems = audit(tmp_path, key, {signature, hash_signature})
    assert any(item.startswith("private root:") for item in problems)
    assert any(item.startswith("private identity literal:") for item in problems)
    assert any(item.startswith("absolute profile path:") for item in problems)
    assert any("escaped.py" in item for item in problems)
    assert any("hash.py" in item for item in problems)
    assert any(item.startswith("uncertified screenshot:") for item in problems)


def test_package_content_scan_detects_identity_and_database():
    script = Path(__file__).resolve().parents[2] / "Packaging" / "Scripts" / "audit_package.py"
    specification = importlib.util.spec_from_file_location("mosaic_package_audit_test", script)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    key = bytes.fromhex("22" * 32)
    module._PRIVACY_KEY = key
    module._SIGNATURES = {hmac.new(key, b"fictional person", hashlib.sha256).hexdigest()}
    assert module.scan_package_bytes(b"compiled literal: Fictional Person") == "Known private identity literal"
    assert module.scan_package_bytes(b"SQLite format 3\0payload") == "Embedded SQLite database"
    assert module.scan_package_bytes(b"safe application schema") is None
