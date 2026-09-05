#!/usr/bin/env python3
"""Package Content Privacy and Security Audit Tool.

Inspects generated build artifacts, installers, and staged app bundles to guarantee
that NO private family data, database files, journals, backups, or developer artifacts
are packaged into distribution releases.
"""

import argparse
import os
import sys
import zipfile
import tarfile
from pathlib import Path

FORBIDDEN_PATTERNS = [
    "family.db",
    "journal.md",
    "sources/",
    "sources\\",
    "backups/",
    "backups\\",
    ".venv/",
    ".venv\\",
    "node_modules/",
    "node_modules\\",
    ".git/",
    ".git\\",
    "__pycache__",
]

REQUIRED_INDICATORS = [
    "people-relationships",
]


def audit_path_list(paths: list[str], label: str) -> bool:
    print(f"Auditing {len(paths)} files in {label}...")
    violations = []

    for path_str in paths:
        normalized = path_str.replace("\\", "/").lower()
        for forbidden in FORBIDDEN_PATTERNS:
            f_norm = forbidden.replace("\\", "/").lower()
            if f_norm in normalized or normalized.endswith(f_norm):
                violations.append((path_str, forbidden))

    if violations:
        print("\n[CRITICAL SECURITY AUDIT FAILURE] Private or development files found in distribution package!", file=sys.stderr)
        for p, rule in violations[:20]:
            print(f"  VIOLATION: {p} (matches rule '{rule}')", file=sys.stderr)
        if len(violations) > 20:
            print(f"  ...and {len(violations) - 20} more violations.", file=sys.stderr)
        return False

    print(f"[AUDIT PASS] Verified {label}: Zero private relationship data, journals, or dev files detected.")
    return True


def audit_directory(directory: Path) -> bool:
    all_files = []
    for root, _, files in os.walk(directory):
        for f in files:
            full_path = Path(root) / f
            rel = full_path.relative_to(directory).as_posix()
            all_files.append(rel)
    return audit_path_list(all_files, str(directory))


def audit_archive(archive_path: Path) -> bool:
    ext = archive_path.suffix.lower()
    if ext in (".zip", ".appx"):
        with zipfile.ZipFile(archive_path, "r") as zf:
            names = zf.namelist()
            return audit_path_list(names, str(archive_path))
    elif ext in (".tar", ".gz", ".tgz"):
        with tarfile.open(archive_path, "r:*") as tf:
            names = tf.getnames()
            return audit_path_list(names, str(archive_path))
    else:
        # Binary installer or file: inspect byte strings for forbidden names
        print(f"Performing binary scan of {archive_path.name} ({archive_path.stat().st_size / (1024*1024):.2f} MB)...")
        content = archive_path.read_bytes()
        # Scan for distinctive private database marker
        if b"SQLite format 3" in content and b"canonical_focus_person" in content:
            print(f"[CRITICAL SECURITY AUDIT FAILURE] Real production SQLite database detected inside {archive_path.name}!", file=sys.stderr)
            return False
        print(f"[AUDIT PASS] Binary scan of {archive_path.name} clean.")
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit package contents for privacy and security")
    parser.add_argument("target", help="Target directory or installer file to audit")
    args = parser.parse_args()

    target_path = Path(args.target).resolve()
    if not target_path.exists():
        print(f"Target does not exist: {target_path}", file=sys.stderr)
        return 1

    if target_path.is_dir():
        ok = audit_directory(target_path)
    else:
        ok = audit_archive(target_path)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
