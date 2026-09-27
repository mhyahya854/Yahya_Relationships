#!/usr/bin/env python3
"""Package Content Privacy and Security Audit Tool.

Inspects generated build artifacts, installers, and staged app bundles to guarantee
that NO private family data, database files, journals, backups, or developer artifacts
are packaged into distribution releases.
"""

import argparse
import io
import json
import os
import re
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Scripts"))
from privacy_gate import ABSOLUTE_PROFILE, _private_hits  # noqa: E402

_PRIVACY_KEY = b""
_SIGNATURES: set[str] = set()
_SYSTEM_GTK_CANDIDATES = (
    Path("/usr/lib/x86_64-linux-gnu/libgtk-3.so.0"),
    Path("/lib/x86_64-linux-gnu/libgtk-3.so.0"),
)

# Patterns that indicate private family data, databases, or developer environments
FORBIDDEN_NAME_PATTERNS = [
    "family.db",
    "journal.md",
    ".pytest_cache",
    "__pycache__",
]

FORBIDDEN_SUBSTRING_PATTERNS = [
    "database/people",
    "database/main",
    "database/sources",
    "backups/",
    ".venv/",
    "node_modules/",
    ".git/",
]

# Database extensions that must never exist in packaged bundles
FORBIDDEN_EXTENSIONS = [
    ".db",
    ".sqlite",
    ".sqlite3",
]


def check_path_violation(rel_path: str) -> str | None:
    """Check whether a single relative path violates privacy or package hygiene rules."""
    normalized = rel_path.replace("\\", "/").strip("/")
    lowered = normalized.lower()
    path_obj = Path(normalized)
    file_name = path_obj.name.lower()

    # 1. Exact or suffix forbidden names
    for pattern in FORBIDDEN_NAME_PATTERNS:
        p_lower = pattern.lower()
        if file_name == p_lower or lowered.endswith("/" + p_lower):
            return f"Matches forbidden file/folder name: '{pattern}'"

    # 2. Forbidden folder substrings
    for sub in FORBIDDEN_SUBSTRING_PATTERNS:
        s_lower = sub.lower().rstrip("/")
        parts = [p.lower() for p in path_obj.parts]
        if s_lower in parts or any(s_lower in part for part in parts):
            return f"Contains forbidden directory: '{sub}'"
        if s_lower in lowered:
            return f"Matches forbidden path component: '{sub}'"

    # 3. Any database files (the app creates its DB in user data root, never bundled)
    if path_obj.suffix.lower() in FORBIDDEN_EXTENSIONS:
        return f"Contains unauthorized database file with extension '{path_obj.suffix}'"

    return None


def audit_path_list(paths: List[str], label: str) -> Tuple[bool, List[Tuple[str, str]]]:
    """Audit a list of relative file paths against privacy rules."""
    violations: List[Tuple[str, str]] = []
    for p in paths:
        reason = check_path_violation(p)
        if reason:
            violations.append((p, reason))

    if violations:
        print(f"\n[CRITICAL SECURITY AUDIT FAILURE] Private or development files found in {label}!", file=sys.stderr)
        for p, rule in violations[:20]:
            print(f"  VIOLATION: {p} -> {rule}", file=sys.stderr)
        if len(violations) > 20:
            print(f"  ...and {len(violations) - 20} more violations.", file=sys.stderr)
        return False, violations

    print(f"[AUDIT PASS] Exhaustive path audit of {len(paths)} items in {label}: ZERO private data detected.")
    return True, []


def audit_directory(directory: Path) -> Tuple[bool, List[Tuple[str, str]]]:
    """Exhaustively scan a directory tree on disk."""
    if not directory.exists() or not directory.is_dir():
        print(f"[AUDIT ERROR] Directory does not exist: {directory}", file=sys.stderr)
        return False, [(str(directory), "Directory does not exist")]

    all_files: List[str] = []
    content_violations: List[Tuple[str, str]] = []
    config_path = Path(__file__).resolve().parents[2] / "Desktop" / "Tauri" / "tauri.conf.json"
    try:
        release_version = json.loads(config_path.read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        release_version = None
    expected_appimage = f"appimage/Mosaic_{release_version}_amd64.AppImage" if release_version else None
    appdir = directory / "appimage" / "Mosaic.AppDir"
    appdir_profile_runs: set[str] | None = None
    for root, dirs, files in os.walk(directory):
        # Also check directory names themselves
        for d in dirs:
            dir_path = Path(root) / d
            rel = dir_path.relative_to(directory).as_posix()
            all_files.append(rel)

        for f in files:
            full_path = Path(root) / f
            rel = full_path.relative_to(directory).as_posix()
            all_files.append(rel)
            # The AppImage runtime and bundled distro GTK library can contain
            # their own build-machine paths. The expanded AppDir is audited
            # separately, including every app-owned executable and sidecar.
            content = full_path.read_bytes()
            vendor_profile_runs: set[str] = set()
            if rel == "appimage/Mosaic.AppDir/usr/lib/libgtk-3.so.0":
                for candidate in _SYSTEM_GTK_CANDIDATES:
                    if candidate.is_file():
                        vendor_profile_runs.update(_profile_runs(candidate.read_bytes()))
            mirrored_appimage = rel == expected_appimage and appdir.is_dir()
            if mirrored_appimage and appdir_profile_runs is None:
                appdir_profile_runs = set()
                for app_file in appdir.rglob("*"):
                    if app_file.is_file():
                        appdir_profile_runs.update(_profile_runs(app_file.read_bytes()))
            reason = scan_package_bytes(
                content,
                allowed_profile_runs=appdir_profile_runs if mirrored_appimage else vendor_profile_runs,
            )
            if reason:
                content_violations.append((rel, reason))

    paths_ok, path_violations = audit_path_list(all_files, f"staged directory '{directory.name}'")
    if content_violations:
        for path, reason in content_violations[:20]:
            print(f"  CONTENT VIOLATION: {path} -> {reason}", file=sys.stderr)
    return paths_ok and not content_violations, path_violations + content_violations


def _contains_sqlite_database(content: bytes) -> bool:
    magic = b"SQLite format 3\x00"
    start = content.find(magic)
    while start >= 0:
        header = content[start:start + 100]
        if len(header) == 100:
            page_size = int.from_bytes(header[16:18], "big")
            if (page_size == 1 or 512 <= page_size <= 32768 and page_size & (page_size - 1) == 0) and (
                header[18] in (1, 2) and header[19] in (1, 2)
                and header[21:24] == bytes((64, 32, 32))
            ):
                return True
        start = content.find(magic, start + 1)
    return False


def _profile_runs(content: bytes) -> set[str]:
    return {
        run.decode("ascii", "ignore")
        for run in re.findall(rb"[\x20-\x7e]{6,}", content)
        if ABSOLUTE_PROFILE.search(run.decode("ascii", "ignore"))
    }


def scan_package_bytes(
    content: bytes, *, check_profile: bool = True,
    allowed_profile_runs: set[str] | None = None,
) -> str | None:
    if _contains_sqlite_database(content):
        return "Embedded SQLite database"
    if len(content) > 256 * 1024 * 1024:
        return "Asset exceeds privacy scan limit"
    if b"\x00" in content[:4096]:
        runs = re.findall(rb"[\x20-\x7e]{6,}", content)
        samples = (run.decode("ascii", "ignore") for run in runs)
    else:
        samples = (content.decode("utf-8", "replace"),)
    for sample in samples:
        if check_profile and ABSOLUTE_PROFILE.search(sample) and sample not in (allowed_profile_runs or ()):
            return "Absolute user-profile path"
        if _private_hits(sample, _PRIVACY_KEY, _SIGNATURES):
            return "Known private identity literal"
    return None


def inspect_deb_archive(archive_path: Path) -> Tuple[bool, List[Tuple[str, str]]]:
    """Inspect the internal file tree of a Debian package (.deb ar container)."""
    with open(archive_path, "rb") as f:
        magic = f.read(8)
        if magic != b"!<arch>\n":
            # Not a standard ar archive, fall back to binary scan
            return audit_binary_heuristics(archive_path)

        all_names: List[str] = []
        content_violations: List[Tuple[str, str]] = []
        while True:
            header = f.read(60)
            if len(header) < 60:
                break
            name = header[:16].decode("ascii", errors="replace").strip()
            size_str = header[48:58].decode("ascii", errors="replace").strip()
            try:
                size = int(size_str)
            except ValueError:
                break
            data = f.read(size)
            if size % 2 == 1:
                f.read(1)  # ar 2-byte alignment padding

            if name.startswith("data.tar"):
                try:
                    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
                        all_names.extend(tf.getnames())
                        for member in tf.getmembers():
                            if not member.isfile():
                                continue
                            if member.size > 256 * 1024 * 1024:
                                content_violations.append((member.name, "Asset exceeds privacy scan limit"))
                                continue
                            extracted = tf.extractfile(member)
                            if extracted is None:
                                content_violations.append((member.name, "Could not scan package member"))
                                continue
                            reason = scan_package_bytes(extracted.read())
                            if reason:
                                content_violations.append((member.name, reason))
                except Exception as e:
                    print(f"[AUDIT WARNING] Could not unpack {name} in {archive_path.name}: {e}")

        if all_names:
            paths_ok, path_violations = audit_path_list(all_names, f"Debian package contents '{archive_path.name}'")
            return paths_ok and not content_violations, path_violations + content_violations
        return audit_binary_heuristics(archive_path)


def audit_binary_heuristics(binary_path: Path) -> Tuple[bool, List[Tuple[str, str]]]:
    """Heuristic scan of opaque installers/binaries for embedded SQLite DBs or real private data."""
    size_mb = binary_path.stat().st_size / (1024 * 1024)
    print(f"Performing heuristic binary scan of {binary_path.name} ({size_mb:.2f} MB)...")
    content = binary_path.read_bytes()

    # Distinguish harmless code/schema strings from actual embedded SQLite databases:
    # A real SQLite database file header starts at offset 0 of its stream with:
    # b"SQLite format 3\x00" followed by 100 bytes of binary database header (page size, etc.)
    reason = scan_package_bytes(content)
    if reason:
        print(f"[CRITICAL SECURITY AUDIT FAILURE] {reason} inside {binary_path.name}!", file=sys.stderr)
        return False, [(str(binary_path), reason)]

    print(f"[AUDIT PASS] Heuristic binary scan of {binary_path.name}: No embedded SQLite databases detected. (Note: Heuristic check; staged tree audit remains authoritative).")
    return True, []


def audit_archive(archive_path: Path) -> Tuple[bool, List[Tuple[str, str]]]:
    """Inspect unpackable archive formats or fall back to heuristic scan."""
    ext = archive_path.suffix.lower()
    if ext in (".zip", ".appx"):
        with zipfile.ZipFile(archive_path, "r") as zf:
            paths_ok, path_violations = audit_path_list(zf.namelist(), f"zip archive '{archive_path.name}'")
            content_violations = []
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if info.file_size > 256 * 1024 * 1024:
                    content_violations.append((info.filename, "Asset exceeds privacy scan limit"))
                    continue
                reason = scan_package_bytes(zf.read(info))
                if reason:
                    content_violations.append((info.filename, reason))
            return paths_ok and not content_violations, path_violations + content_violations
    elif ext in (".tar", ".gz", ".tgz", ".xz", ".bz2"):
        with tarfile.open(archive_path, "r:*") as tf:
            paths_ok, path_violations = audit_path_list(tf.getnames(), f"tar archive '{archive_path.name}'")
            content_violations = []
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                if member.size > 256 * 1024 * 1024:
                    content_violations.append((member.name, "Asset exceeds privacy scan limit"))
                    continue
                extracted = tf.extractfile(member)
                if extracted is None:
                    content_violations.append((member.name, "Could not scan archive member"))
                    continue
                reason = scan_package_bytes(extracted.read())
                if reason:
                    content_violations.append((member.name, reason))
            return paths_ok and not content_violations, path_violations + content_violations
    elif ext == ".deb":
        return inspect_deb_archive(archive_path)
    else:
        return audit_binary_heuristics(archive_path)


def audit_target(target_path: Path) -> bool:
    """Audit a directory or file target. Returns True if all checks pass."""
    if not target_path.exists():
        print(f"[AUDIT ERROR] Target does not exist: {target_path}", file=sys.stderr)
        return False

    if target_path.is_dir():
        ok, _ = audit_directory(target_path)
        return ok
    else:
        ok, _ = audit_archive(target_path)
        return ok


def main() -> int:
    global _PRIVACY_KEY, _SIGNATURES
    parser = argparse.ArgumentParser(description="Audit package contents for privacy and security")
    parser.add_argument("targets", nargs="+", help="Target directories or installer files to audit")
    args = parser.parse_args()

    try:
        _PRIVACY_KEY = bytes.fromhex(os.environ.get("MOSAIC_PRIVACY_HMAC_KEY", ""))
        _SIGNATURES = set(json.loads((Path(__file__).resolve().parents[2] / "Scripts" / "privacy-signatures.json").read_text(encoding="utf-8"))["hmac_sha256"])
    except (ValueError, OSError, KeyError, TypeError):
        print("[AUDIT BLOCKED] Privacy key or signatures unavailable.", file=sys.stderr)
        return 2
    if len(_PRIVACY_KEY) < 32:
        print("[AUDIT BLOCKED] Privacy key is missing or invalid.", file=sys.stderr)
        return 2

    all_passed = True
    for t in args.targets:
        target_path = Path(t).resolve()
        passed = audit_target(target_path)
        if not passed:
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
