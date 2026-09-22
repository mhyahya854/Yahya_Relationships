"""Canonical person and unresolved person identity generation and validation.

Governed by Master Plan:
- Known persons: normalized_full_name--INITIALS##
  Examples:
    sara_khan--SK01
    sara_khan--SK02
    sara_ahmed_khan--SAK01
    mohammad_yahya_hussain--MYH01

- Unresolved persons: unknown_person--UP0001, unknown_person--UP0002, ...
"""

from __future__ import annotations

import re
import unicodedata
from typing import Collection, Iterable

CANONICAL_KNOWN_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*--[A-Z]+[0-9]{2}$")
UNRESOLVED_RE = re.compile(r"^unknown_person--UP[0-9]{4}$")


def normalize_name(name: str) -> str:
    """Normalize a display name into a portable lowercase identifier stem.

    Accented Latin text is folded to ASCII. Other Unicode letters and digits are
    represented by stable ``uXXXX`` code-point tokens rather than collapsing
    unrelated names to a guessed ``person`` identifier.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("A non-empty person name is required for a canonical ID.")

    normalized = unicodedata.normalize("NFKD", name.strip())
    tokens: list[str] = []
    current: list[str] = []
    for char in normalized:
        if unicodedata.combining(char):
            continue
        if char.isascii() and char.isalnum():
            current.append(char.lower())
        elif char.isalnum():
            current.append(f"u{ord(char):04x}")
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    if not tokens:
        raise ValueError("The person name has no usable letters or digits.")
    return "_".join(tokens)


def compute_initials(name: str) -> str:
    """Compute uppercase initials representing all full-name components."""
    normalized = normalize_name(name)
    return "".join(token[0].upper() for token in normalized.split("_") if token)


def generate_canonical_person_id(name: str, existing_ids: Iterable[str] | Collection[str] = ()) -> str:
    """Generate a stable canonical known-person ID: normalized_full_name--INITIALS##.

    Collision counter starts at 01 and deterministically increments if an
    identical normalized name + initials base already exists in existing_ids.
    """
    normalized = normalize_name(name)
    initials = compute_initials(normalized)
    base = f"{normalized}--{initials}"
    existing_set = set(existing_ids)

    for counter in range(1, 100):
        candidate = f"{base}{counter:02d}"
        if candidate not in existing_set:
            return candidate
    raise ValueError(f"Canonical ID counter exhausted for normalized name '{normalized}'.")


def is_valid_canonical_person_id(person_id: str) -> bool:
    """Check whether person_id strictly satisfies the known-person canonical format."""
    if not isinstance(person_id, str):
        return False
    return bool(CANONICAL_KNOWN_RE.fullmatch(person_id))


def is_valid_unresolved_person_id(unresolved_id: str) -> bool:
    """Check whether unresolved_id strictly satisfies the unknown-person canonical format."""
    if not isinstance(unresolved_id, str):
        return False
    return bool(UNRESOLVED_RE.fullmatch(unresolved_id))


def generate_unresolved_person_id(existing_ids: Iterable[str] | Collection[str] = ()) -> str:
    """Allocate the next sequential unknown_person--UP#### identifier."""
    existing_set = set(existing_ids)
    for counter in range(1, 10000):
        candidate = f"unknown_person--UP{counter:04d}"
        if candidate not in existing_set:
            return candidate
    raise ValueError("Unresolved-person ID space is exhausted.")
