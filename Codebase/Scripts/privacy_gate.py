"""Fail-closed public source and package privacy gate.

Run before committing, in CI, and before packaging. Identity signatures are
keyed HMACs; the key stays outside Git and is required for a passing audit.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PRIVATE_ROOTS = {"Database", "People", "Backups", "Raw", "Media", "Mosaic - Local Private Data", "Local Private Data"}
ABSOLUTE_PROFILE = re.compile(
    r"(?i)(?:[a-z]:[\\/]+" + "users" + r"[\\/]+|/" + "users" + r"/[^/\s]+/|/" + "home" + r"/[^/\s]+/)"
)
WORDS = re.compile(r"[\w-]+", re.UNICODE)
SCREENSHOT_ROOT = "Documentation/UI-Screenshots/"
SYNTHETIC_MARKER = "SYNTHETIC_FIXTURE"
TEXT_LIMIT = 8 * 1024 * 1024


def _git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL)


def _signature_candidates(content: str):
    words = WORDS.findall(content.casefold())
    for index, word in enumerate(words):
        yield word
        for count in range(2, 6):
            if index + count <= len(words):
                yield " ".join(words[index:index + count])


def _private_hits(content: str, key: bytes, signatures: set[str]) -> bool:
    for candidate in _signature_candidates(content):
        digest = hmac.new(key, candidate.encode("utf-8"), hashlib.sha256).hexdigest()
        if digest in signatures:
            return True
    return False


def _paths(root: Path) -> list[str]:
    return [item.decode("utf-8", "surrogateescape") for item in _git(root, "ls-files", "--cached", "-z").split(b"\0") if item]


def audit(root: Path, key: bytes, signatures: set[str]) -> list[str]:
    problems: list[str] = []
    tracked = _paths(root)
    manifests = {}
    for path in tracked:
        if path.startswith(SCREENSHOT_ROOT) and path.endswith("MANIFEST.md"):
            try:
                manifests[path] = _git(root, "show", ":" + path).decode("utf-8", "replace")
            except subprocess.CalledProcessError:
                manifests[path] = ""
    for path in tracked:
        parts = Path(path).parts
        if parts and parts[0] in PRIVATE_ROOTS:
            problems.append(f"private root: {path}")
            continue
        suffix = Path(path).suffix.lower()
        if suffix in {".db", ".sqlite", ".sqlite3", ".db3"}:
            problems.append(f"database asset: {path}")
            continue
        if path.startswith(SCREENSHOT_ROOT) and suffix in {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".zip"}:
            parent = Path(path).parent.as_posix()
            manifest = f"{parent}/MANIFEST.md"
            if SYNTHETIC_MARKER not in manifests.get(manifest, ""):
                problems.append(f"uncertified screenshot: {path}")
            continue
        try:
            staged = _git(root, "show", ":" + path)
        except subprocess.CalledProcessError:
            problems.append(f"unreadable staged asset: {path}")
            continue
        if staged.startswith(b"SQLite format 3\0"):
            problems.append(f"embedded SQLite asset: {path}")
            continue
        if len(staged) > TEXT_LIMIT or b"\0" in staged[:4096]:
            continue
        content = staged.decode("utf-8", "replace")
        if ABSOLUTE_PROFILE.search(content):
            problems.append(f"absolute profile path: {path}")
        if _private_hits(content, key, signatures):
            problems.append(f"private identity literal: {path}")
        working = root / path
        if working.is_file() and working.stat().st_size <= TEXT_LIMIT:
            working_bytes = working.read_bytes()
            if working_bytes != staged and b"\0" not in working_bytes[:4096]:
                draft = working_bytes.decode("utf-8", "replace")
                if ABSOLUTE_PROFILE.search(draft):
                    problems.append(f"absolute profile path in working copy: {path}")
                if _private_hits(draft, key, signatures):
                    problems.append(f"private identity literal in working copy: {path}")
    return sorted(set(problems))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--signatures", type=Path, default=Path(__file__).with_name("privacy-signatures.json"))
    arguments = parser.parse_args()
    raw_key = os.environ.get("MOSAIC_PRIVACY_HMAC_KEY", "")
    try:
        key = bytes.fromhex(raw_key)
    except ValueError:
        key = b""
    if len(key) < 32:
        print("PRIVACY GATE BLOCKED: MOSAIC_PRIVACY_HMAC_KEY is missing or invalid.")
        return 2
    try:
        signatures = set(json.loads(arguments.signatures.read_text(encoding="utf-8"))["hmac_sha256"])
    except (OSError, ValueError, KeyError, TypeError):
        print("PRIVACY GATE BLOCKED: identity signatures are unavailable.")
        return 2
    problems = audit(arguments.repo.resolve(), key, signatures)
    for problem in problems:
        print("PRIVACY GATE FAIL:", problem)
    print(f"PRIVACY GATE: {'FAIL' if problems else 'PASS'} ({len(problems)} findings)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
