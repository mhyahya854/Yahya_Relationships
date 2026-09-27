"""Privacy gate behavior on a temporary public repository."""

import hashlib
import hmac
import importlib.util
import json
import sqlite3
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


def test_package_content_scan_detects_identity_and_database(tmp_path):
    script = Path(__file__).resolve().parents[2] / "Packaging" / "Scripts" / "audit_package.py"
    specification = importlib.util.spec_from_file_location("mosaic_package_audit_test", script)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    key = bytes.fromhex("22" * 32)
    module._PRIVACY_KEY = key
    module._SIGNATURES = {hmac.new(key, b"fictional person", hashlib.sha256).hexdigest()}
    assert module.scan_package_bytes(b"compiled literal: Fictional Person") == "Known private identity literal"
    database_path = tmp_path / "synthetic.db"
    connection = sqlite3.connect(database_path)
    connection.execute("CREATE TABLE synthetic (id INTEGER)")
    connection.close()
    database = database_path.read_bytes()
    assert module.scan_package_bytes(b"binary prefix" + database) == "Embedded SQLite database"
    assert module.scan_package_bytes(b"SQLite format 3\0payload") is None
    assert module.scan_package_bytes(b"\0/" + b"home/vendor/build", check_profile=False) is None
    assert module.scan_package_bytes(b"\0Fictional Person", check_profile=False) == "Known private identity literal"
    assert module.scan_package_bytes(b"safe application schema") is None


def test_package_audit_checks_app_owned_binary_while_tolerating_vendor_build_paths(tmp_path):
    script = Path(__file__).resolve().parents[2] / "Packaging" / "Scripts" / "audit_package.py"
    specification = importlib.util.spec_from_file_location("mosaic_package_audit_vendor_test", script)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    module._PRIVACY_KEY = bytes.fromhex("22" * 32)
    module._SIGNATURES = set()
    vendor_profile = b"\0/" + b"home/vendor/build"
    private_profile = b"\0/" + b"home/somebody/private"
    bundle = tmp_path / "bundle"
    appdir = bundle / "appimage" / "Mosaic.AppDir"
    library = appdir / "usr" / "lib" / "libgtk-3.so.0"
    library.parent.mkdir(parents=True)
    library.write_bytes(vendor_profile)
    trusted_library = tmp_path / "trusted-system-libgtk.so"
    trusted_library.write_bytes(library.read_bytes())
    module._SYSTEM_GTK_CANDIDATES = (trusted_library,)
    version = json.loads((Path(__file__).resolve().parents[2] / "Desktop" / "Tauri" / "tauri.conf.json").read_text(encoding="utf-8"))["version"]
    appimage = appdir.parent / f"Mosaic_{version}_amd64.AppImage"
    appimage.write_bytes(vendor_profile)
    app_binary = appdir / "usr" / "bin" / "mosaic"
    app_binary.parent.mkdir(parents=True)
    app_binary.write_bytes(b"\0safe application")
    assert module.audit_directory(bundle)[0]
    appimage.write_bytes(private_profile)
    ok, violations = module.audit_directory(bundle)
    assert not ok
    assert any(path.endswith(appimage.name) and reason == "Absolute user-profile path" for path, reason in violations)
    appimage.write_bytes(vendor_profile)
    library.write_bytes(vendor_profile + b"\0packager-patched")
    assert module.audit_directory(bundle)[0]
    unrelated = appdir.parent / "Evil.AppImage"
    unrelated.write_bytes(private_profile)
    ok, violations = module.audit_directory(bundle)
    assert not ok
    assert any(path.endswith("Evil.AppImage") and reason == "Absolute user-profile path" for path, reason in violations)
    unrelated.unlink()
    nested = bundle / "attacker" / "usr" / "lib" / "libgtk-3.so.0"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(private_profile)
    ok, violations = module.audit_directory(bundle)
    assert not ok
    assert any(path.endswith("attacker/usr/lib/libgtk-3.so.0") and reason == "Absolute user-profile path" for path, reason in violations)
    nested.unlink()
    library.write_bytes(private_profile)
    ok, violations = module.audit_directory(bundle)
    assert not ok
    assert any(path.endswith("Mosaic.AppDir/usr/lib/libgtk-3.so.0") and reason == "Absolute user-profile path" for path, reason in violations)
    library.write_bytes(trusted_library.read_bytes())
    app_binary.write_bytes(private_profile)
    ok, violations = module.audit_directory(bundle)
    assert not ok
    assert any(path.endswith("usr/bin/mosaic") and reason == "Absolute user-profile path" for path, reason in violations)


def test_package_audit_limits_vendor_run_digests_to_exact_appimage(tmp_path):
    script = Path(__file__).resolve().parents[2] / "Packaging" / "Scripts" / "audit_package.py"
    specification = importlib.util.spec_from_file_location("mosaic_package_audit_digest_test", script)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    module._PRIVACY_KEY = bytes.fromhex("22" * 32)
    module._SIGNATURES = set()
    vendor_run = b"stencil-export=/" + b"home/vendor/dev/RESOURCES/synthetic.svg"
    approved = hashlib.sha256(vendor_run).hexdigest()
    module._APPIMAGE_VENDOR_PROFILE_DIGESTS = frozenset({approved})
    bundle = tmp_path / "bundle"
    appdir = bundle / "appimage" / "Mosaic.AppDir"
    appdir.mkdir(parents=True)
    version = json.loads((Path(__file__).resolve().parents[2] / "Desktop" / "Tauri" / "tauri.conf.json").read_text(encoding="utf-8"))["version"]
    appimage = appdir.parent / f"Mosaic_{version}_amd64.AppImage"
    appimage.write_bytes(b"\0" + vendor_run)
    assert module.audit_directory(bundle)[0]

    appimage.write_bytes(b"\0" + vendor_run + b"-changed")
    assert not module.audit_directory(bundle)[0]
    appimage.write_bytes(b"\0" + vendor_run)
    other_version = appdir.parent / "Mosaic_0.0.0_amd64.AppImage"
    appimage.rename(other_version)
    assert not module.audit_directory(bundle)[0]
    other_version.rename(appimage)
    unrelated = appdir.parent / "Evil.AppImage"
    unrelated.write_bytes(b"\0" + vendor_run)
    assert not module.audit_directory(bundle)[0]
    unrelated.unlink()

    module._SIGNATURES = {hmac.new(module._PRIVACY_KEY, b"synthetic", hashlib.sha256).hexdigest()}
    assert module.scan_package_bytes(
        b"\0" + vendor_run,
        allowed_profile_run_digests=frozenset({approved}),
    ) == "Known private identity literal"
    database = tmp_path / "synthetic.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE synthetic (id INTEGER)")
    connection.close()
    assert module.scan_package_bytes(
        b"\0" + vendor_run + b"\0" + database.read_bytes(),
        allowed_profile_run_digests=frozenset({approved}),
    ) == "Embedded SQLite database"
