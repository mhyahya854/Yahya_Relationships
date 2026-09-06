"""Relationship display-language layer.

The kinship engine returns deterministic canonical labels (English + Urdu)
derived from structured facts. This layer attaches a stable semantic type key
to each result so future display languages can be added without touching the
kinship code. Known keys are normalised here; unknown phrases keep their
engine label and receive a stable ``family/custom:*`` key.
"""

from __future__ import annotations

import re

SIDE_WORDS = ("maternal", "paternal")
REMOVAL_WORDS = {
    "once removed": 1,
    "twice removed": 2,
}

# (normalised english label) -> (semantic type, english canonical, urdu)
KNOWN_LABELS = {
    "self": ("self", "Self", "خود"),
    "husband": ("husband", "Husband", "شوہر"),
    "wife": ("wife", "Wife", "بیوی"),
    "father": ("father", "Father", "والد"),
    "mother": ("mother", "Mother", "والدہ"),
    "parent": ("parent", "Parent", "والدین"),
    "son": ("son", "Son", "بیٹا"),
    "daughter": ("daughter", "Daughter", "بیٹی"),
    "child": ("child", "Child", "بچہ"),
    "brother": ("brother", "Brother", "بھائی"),
    "sister": ("sister", "Sister", "بہن"),
    "full brother": ("full_brother", "Full brother", "سگا بھائی"),
    "full sister": ("full_sister", "Full sister", "سگی بہن"),
    "half brother": ("half_brother", "Half brother", "سوتیلا بھائی"),
    "half sister": ("half_sister", "Half sister", "سوتیلی بہن"),
    "grandfather": ("grandfather", "Grandfather", "دادا"),
    "grandmother": ("grandmother", "Grandmother", "دادی"),
    "maternal grandfather": (
        "maternal_grandfather",
        "Maternal grandfather",
        "نانا",
    ),
    "maternal grandmother": (
        "maternal_grandmother",
        "Maternal grandmother",
        "نانی",
    ),
    "paternal grandfather": (
        "paternal_grandfather",
        "Paternal grandfather",
        "دادا",
    ),
    "paternal grandmother": (
        "paternal_grandmother",
        "Paternal grandmother",
        "دادی",
    ),
    "great-grandfather": ("great_grandfather", "Great-grandfather", None),
    "great-grandmother": ("great_grandmother", "Great-grandmother", None),
    "maternal great-grandfather": ("maternal_great_grandfather", "Maternal great-grandfather", None),
    "maternal great-grandmother": ("maternal_great_grandmother", "Maternal great-grandmother", None),
    "paternal great-grandfather": ("paternal_great_grandfather", "Paternal great-grandfather", None),
    "paternal great-grandmother": ("paternal_great_grandmother", "Paternal great-grandmother", None),
    "grandson": ("grandson", "Grandson", "پوتا"),
    "granddaughter": ("granddaughter", "Granddaughter", "پوتی"),
    "great-grandson": ("great_grandson", "Great-grandson", None),
    "great-granddaughter": ("great_granddaughter", "Great-granddaughter", None),
    "maternal uncle": ("maternal_uncle", "Maternal uncle", "ماموں"),
    "paternal uncle": ("paternal_uncle", "Paternal uncle", "چچا"),
    "uncle": ("uncle", "Uncle", "چچا"),
    "maternal aunt": ("maternal_aunt", "Maternal aunt", "خالہ"),
    "paternal aunt": ("paternal_aunt", "Paternal aunt", "پھوپھی"),
    "aunt": ("aunt", "Aunt", "پھوپھی"),
    "great-uncle": ("great_uncle", "Great-uncle", None),
    "great-aunt": ("great_aunt", "Great-aunt", None),
    "maternal great-uncle": ("maternal_great_uncle", "Maternal great-uncle", None),
    "maternal great-aunt": ("maternal_great_aunt", "Maternal great-aunt", None),
    "paternal great-uncle": ("paternal_great_uncle", "Paternal great-uncle", None),
    "paternal great-aunt": ("paternal_great_aunt", "Paternal great-aunt", None),
    "nephew": ("nephew", "Nephew", "بھانجا"),
    "niece": ("niece", "Niece", "بھانجی"),
    "grandnephew": ("grandnephew", "Grandnephew", None),
    "grandniece": ("grandniece", "Grandniece", None),
    "great-grandnephew": ("great_grandnephew", "Great-grandnephew", None),
    "great-grandniece": ("great_grandniece", "Great-grandniece", None),
}


def _strip_suffix(en: str) -> tuple[str, str | None]:
    match = re.search(r"\s*\(([a-z]+)\)\s*$", en, re.IGNORECASE)
    if match:
        return en[: match.start()].strip(), match.group(1).lower()
    return en, None


def _side_of(en: str) -> tuple[str, str]:
    lowered = en.lower()
    for side in SIDE_WORDS:
        if lowered.startswith(side + " "):
            return en[len(side) + 1 :], side
    return en, ""


def _cousin_type(phrase: str) -> tuple[str, str, int, int, str] | None:
    """Parse 'maternal second cousin once removed' style phrases.

    Returns: (type_key, display, degree, removal, side)
    """
    normalized = " ".join(phrase.lower().split())
    if "cousin" not in normalized:
        return None
    ordinal_words = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
    }
    removal = 0
    for word, value in REMOVAL_WORDS.items():
        if word in normalized:
            removal = value
            normalized = normalized.replace(word, "").strip()
    for match in re.finditer(r"(\d+) times removed", normalized):
        removal = int(match.group(1))
        normalized = normalized.replace(match.group(0), "").strip()
    side = ""
    for word in SIDE_WORDS:
        if normalized.startswith(word):
            side = word
            normalized = normalized.replace(word, "", 1).strip()
    head = normalized.replace("cousin", "").strip()
    degree = ordinal_words.get(head)
    if degree is None and head.isdigit():
        degree = int(head)
    if degree is None:
        return None

    # Stable canonical semantic key with explicit degree and removal
    side_prefix = f"{side}_" if side else ""
    type_key = f"{side_prefix}cousin_degree_{degree}_removed_{removal}"
    suffix = "s" if phrase.strip().endswith("s") else ""
    display = " ".join(
        part
        for part in (
            side,
            _ordinal_en(degree),
            f"cousin{suffix}",
            _removal_en(removal),
        )
        if part
    )
    return type_key, display, degree, removal, side


def _ordinal_en(degree: int) -> str:
    words = {
        1: "first",
        2: "second",
        3: "third",
        4: "fourth",
        5: "fifth",
        6: "sixth",
        7: "seventh",
        8: "eighth",
        9: "ninth",
        10: "tenth",
    }
    return words.get(degree, f"{degree}th")


def _removal_en(removal: int) -> str:
    if removal == 1:
        return "once removed"
    if removal == 2:
        return "twice removed"
    if removal > 2:
        return f"{removal} times removed"
    return ""


def normalize_family_entry(entry: dict) -> dict:
    """Attach ``relationship_type``, ``semantic_id``, and structured metadata
    to one engine relationship entry.

    The engine remains authoritative for the label strings; this function is
    a pure deterministic display/indexing layer.
    """
    en = entry.get("en") or ""
    ur = entry.get("ur")
    base_en, suffix = _strip_suffix(en)
    stripped, explicit_side = _side_of(base_en)
    type_key = None
    canonical_en = base_en
    canonical_ur = ur
    side: str | None = explicit_side or None
    degree: int | None = None
    removal: int | None = None

    # Check known labels first
    known = KNOWN_LABELS.get(base_en.lower())
    if known is None:
        known = KNOWN_LABELS.get(stripped.lower())
    if known is not None:
        type_key, canonical_en, canonical_ur = known
        if "maternal" in base_en.lower():
            side = "maternal"
        elif "paternal" in base_en.lower():
            side = "paternal"
    else:
        cousin = _cousin_type(base_en)
        if cousin is not None:
            type_key, canonical_en, degree, removal, cousin_side = cousin
            if cousin_side:
                side = cousin_side

    if type_key is None:
        # Generational great- prefixes
        norm_clean = base_en.lower().replace("-", "_")
        slug = re.sub(r"[^a-z0-9]+", "_", norm_clean).strip("_")
        type_key = f"family_{slug or 'unknown'}"
        canonical_en = base_en
    if suffix:
        type_key = f"{type_key}_{suffix}"
    if not canonical_ur and suffix:
        canonical_ur = None

    derived = entry.get("derived")
    if derived is None:
        # Explicit primary parent/marriage/self are not derived; cousins and generational blood roles are derived
        derived = entry.get("group") not in ("primary",) if "group" in entry else True

    return {
        "domain": "family",
        "relationship_type": type_key,
        "semantic_id": type_key,
        "label_en": canonical_en + (f" ({suffix})" if suffix else ""),
        "label_ur": canonical_ur,
        "side": side,
        "degree": degree,
        "removal": removal,
        "derived": derived,
    }


def normalize_general_entry(
    row,
    *,
    from_person: str,
    label_a_to_b: str | None,
    label_b_to_a: str | None,
) -> dict:
    directionality = row["directionality"]
    if directionality == "directional":
        is_forward = row["direction_from"] == from_person
        label = label_a_to_b if is_forward else label_b_to_a
        reverse_label = label_b_to_a if is_forward else label_a_to_b
    else:
        label = label_a_to_b or label_b_to_a
        reverse_label = label
    type_key = row["type"]
    return {
        "domain": "general",
        "relationship_type": type_key,
        "semantic_id": f"general_{type_key}",
        "label_en": label,
        "label_ur": None,
        "derived": False,
        "directionality": directionality,
        "reverse_label_en": reverse_label,
        "notes": row["notes"],
    }
