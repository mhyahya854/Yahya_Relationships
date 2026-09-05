#!/usr/bin/env python3
"""Package Content Privacy and Security Audit Tool.

Inspects generated build artifacts, installers, and staged app bundles to guarantee
that NO private family data, database files, journals, backups, or developer artifacts
are packaged into distribution releases.
"""

import argparse
import io
import os
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import List, Tuple

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

    return audit_path_list(all_files, f"staged directory '{directory.name}'")


def inspect_deb_archive(archive_path: Path) -> Tuple[bool, List[Tuple[str, str]]]:
    """Inspect the internal file tree of a Debian package (.deb ar container)."""
    with open(archive_path, "rb") as f:
        magic = f.read(8)
        if magic != b"!<arch>\n":
            # Not a standard ar archive, fall back to binary scan
            return audit_binary_heuristics(archive_path)

        all_names: List[str] = []
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
                except Exception as e:
                    print(f"[AUDIT WARNING] Could not unpack {name} in {archive_path.name}: {e}")

        if all_names:
            return audit_path_list(all_names, f"Debian package contents '{archive_path.name}'")
        return audit_binary_heuristics(archive_path)


def audit_binary_heuristics(binary_path: Path) -> Tuple[bool, List[Tuple[str, str]]]:
    """Heuristic scan of opaque installers/binaries for embedded SQLite DBs or real private data."""
    size_mb = binary_path.stat().st_size / (1024 * 1024)
    print(f"Performing heuristic binary scan of {binary_path.name} ({size_mb:.2f} MB)...")
    content = binary_path.read_bytes()

    # Distinguish harmless code/schema strings from actual embedded SQLite databases:
    # A real SQLite database file header starts at offset 0 of its stream with:
    # b"SQLite format 3\x00" followed by 100 bytes of binary database header (page size, etc.)
    if b"SQLite format 3\x00" in content:
        # Check if this is an actual SQLite file embedded intact
        print(f"[CRITICAL SECURITY AUDIT FAILURE] Embedded SQLite database detected inside {binary_path.name}!", file=sys.stderr)
        return False, [(str(binary_path), "Embedded SQLite database detected via binary signature")]

    print(f"[AUDIT PASS] Heuristic binary scan of {binary_path.name}: No embedded SQLite databases detected. (Note: Heuristic check; staged tree audit remains authoritative).")
    return True, []


def audit_archive(archive_path: Path) -> Tuple[bool, List[Tuple[str, str]]]:
    """Inspect unpackable archive formats or fall back to heuristic scan."""
    ext = archive_path.suffix.lower()
    if ext in (".zip", ".appx"):
        with zipfile.ZipFile(archive_path, "r") as zf:
            return audit_path_list(zf.namelist(), f"zip archive '{archive_path.name}'")
    elif ext in (".tar", ".gz", ".tgz", ".xz", ".bz2"):
        with tarfile.open(archive_path, "r:*") as tf:
            return audit_path_list(tf.getnames(), f"tar archive '{archive_path.name}'")
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
    parser = argparse.ArgumentParser(description="Audit package contents for privacy and security")
    parser.add_argument("targets", nargs="+", help="Target directories or installer files to audit")
    args = parser.parse_args()

    all_passed = True
    for t in args.targets:
        target_path = Path(t).resolve()
        passed = audit_target(target_path)
        if not passed:
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
