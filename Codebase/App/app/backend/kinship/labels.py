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


GRAND_ANCESTOR_UR = {
    ("maternal", "male"): "نانا",
    ("maternal", "female"): "نانی",
    ("paternal", "male"): "دادا",
    ("paternal", "female"): "دادی",
}
UNCLE_AUNT_UR = {
    ("maternal", "male"): "ماموں",
    ("maternal", "female"): "خالہ",
    ("paternal", "male"): "چچا",
    ("paternal", "female"): "پھوپھی",
}
COUSIN_UR_ZERO_REMOVAL = {
    1: "پہلے کزن",
    2: "دوسرے کزن",
    3: "تیسرے کزن",
}


def _cousin_ur(degree: int, removal: int) -> str | None:
    if removal == 0:
        return COUSIN_UR_ZERO_REMOVAL.get(degree)
    return None


def structured_family_semantic(
    entry: dict,
) -> tuple[str, str, str | None, int | None, int | None, str | None] | None:
    """Derive language-neutral semantic identity from structured kinship facts.

    Returns: (semantic_id, canonical_en, canonical_ur, degree, removal, side)
    or None if the entry lacks structured metadata and must fall back to legacy parsing.
    """
    # 1. Direct explicit semantic_id override
    if entry.get("semantic_id"):
        sem_id = entry["semantic_id"]
        en = entry.get("en") or entry.get("label_en") or sem_id
        ur = entry.get("ur") or entry.get("label_ur")
        degree = entry.get("degree")
        removal = entry.get("removal")
        side = entry.get("side")
        return (sem_id, en, ur, degree, removal, side)

    kind = entry.get("kind") or entry.get("fact_kind")
    if not kind and entry.get("degree") is not None:
        kind = "collateral"

    if not kind:
        return None

    target_gender = entry.get("target_gender")
    side = entry.get("side") or ""
    side_prefix = f"{side}_" if side in ("maternal", "paternal") else ""
    side_word = f"{side.capitalize()} " if side in ("maternal", "paternal") else ""

    if kind == "self":
        return ("self", entry.get("en") or "Self", entry.get("ur") or "خود", None, None, None)

    if kind == "marriage":
        if target_gender == "female" or entry.get("relationship_type") == "wife":
            return ("wife", entry.get("en") or "Wife", entry.get("ur") or "بیوی", None, None, None)
        return ("husband", entry.get("en") or "Husband", entry.get("ur") or "شوہر", None, None, None)

    if kind == "parent_child":
        role = entry.get("role")
        suffix = (
            entry.get("suffix")
            or (entry.get("child_kind") if entry.get("child_kind") != "biological" else None)
            or (entry.get("parent_kind") if entry.get("parent_kind") != "biological" else None)
            or (entry.get("kind_detail") if entry.get("kind_detail") != "biological" else None)
        )
        if role in ("son", "daughter", "child") or entry.get("direction") == "child":
            base = "son" if target_gender == "male" else ("daughter" if target_gender == "female" else "child")
            en_base = "Son" if target_gender == "male" else ("Daughter" if target_gender == "female" else "Child")
            ur_base = "بیٹا" if target_gender == "male" else ("بیٹی" if target_gender == "female" else "بچہ")
        else:
            if role in ("mother", "father"):
                base = role
                en_base = role.capitalize()
                ur_base = "والدہ" if role == "mother" else "والد"
            elif target_gender == "female":
                base, en_base, ur_base = "mother", "Mother", "والدہ"
            elif target_gender == "male":
                base, en_base, ur_base = "father", "Father", "والد"
            else:
                base, en_base, ur_base = "parent", "Parent", "والدین"
        if suffix:
            sem_id = f"{base}_{suffix}"
            en_label = f"{en_base} ({suffix})"
            ur_label = None
        else:
            sem_id = base
            en_label = en_base
            ur_label = ur_base
        return (sem_id, entry.get("en") or en_label, entry.get("ur") or ur_label, None, None, None)

    if kind == "sibling":
        stype = entry.get("sibling_type") or ("full" if entry.get("explicit_full") else None)
        if stype == "full":
            sem_id = "full_sister" if target_gender == "female" else "full_brother"
            en_base = "Full sister" if target_gender == "female" else "Full brother"
            ur_base = "سگی بہن" if target_gender == "female" else "سگا بھائی"
        elif stype == "half":
            sem_id = "half_sister" if target_gender == "female" else "half_brother"
            en_base = "Half sister" if target_gender == "female" else "Half brother"
            ur_base = "سوتیلی بہن" if target_gender == "female" else "سوتیلا بھائی"
        else:
            sem_id = "sister" if target_gender == "female" else "brother"
            en_base = "Sister" if target_gender == "female" else "Brother"
            ur_base = "بہن" if target_gender == "female" else "بھائی"
        return (sem_id, entry.get("en") or en_base, entry.get("ur") or ur_base, None, None, None)

    if kind == "ancestor":
        distance = entry.get("distance", 2)
        base = "grandfather" if target_gender == "male" else "grandmother"
        base_cap = base.capitalize()
        if distance == 2:
            sem_id = f"{side_prefix}{base}"
            en_base = f"{side_word}{base_cap}".strip()
            ur_base = GRAND_ANCESTOR_UR.get((side, target_gender))
        elif distance == 3:
            sem_id = f"{side_prefix}great_{base}"
            en_base = f"{side_word}Great-{base}".strip()
            ur_base = None
        else:
            prefix_id = "great_" * (distance - 2)
            prefix_en = "great-" * (distance - 2)
            sem_id = f"{side_prefix}{prefix_id}{base}"
            en_base = f"{side_word}{prefix_en}{base}".strip().capitalize()
            ur_base = None
        return (sem_id, entry.get("en") or en_base, entry.get("ur") or ur_base, None, None, side or None)

    if kind == "descendant":
        distance = entry.get("distance", 2)
        base = "grandson" if target_gender == "male" else "granddaughter"
        base_cap = base.capitalize()
        if distance == 2:
            sem_id = base
            en_base = base_cap
            ur_base = "پوتا" if target_gender == "male" else "پوتی"
        elif distance == 3:
            sem_id = f"great_{base}"
            en_base = f"Great-{base}"
            ur_base = None
        else:
            prefix_id = "great_" * (distance - 2)
            prefix_en = "great-" * (distance - 2)
            sem_id = f"{prefix_id}{base}"
            en_base = f"{prefix_en}{base}".capitalize()
            ur_base = None
        return (sem_id, entry.get("en") or en_base, entry.get("ur") or ur_base, None, None, None)

    if kind == "collateral":
        da = entry.get("da", 0)
        db = entry.get("db", 0)
        if da == 1 and db == 1:
            sem_id = "half_sister" if target_gender == "female" else "half_brother"
            en_base = "Half sister" if target_gender == "female" else "Half brother"
            ur_base = "سوتیلی بہن" if target_gender == "female" else "سوتیلا بھائی"
            return (sem_id, entry.get("en") or en_base, entry.get("ur") or ur_base, None, None, None)
        if da == 1 and db >= 2:
            depth = db - 1
            base = "niece" if target_gender == "female" else "nephew"
            base_cap = base.capitalize()
            if depth == 1:
                sem_id = base
                en_base = base_cap
                ur_base = "بھانجی" if target_gender == "female" else "بھانجا"
            elif depth == 2:
                sem_id = f"grand{base}"
                en_base = f"Grand{base}"
                ur_base = None
            else:
                prefix_id = "great_" * (depth - 2) + "grand"
                prefix_en = "great-" * (depth - 2) + "grand"
                sem_id = f"{prefix_id}{base}"
                en_base = f"{prefix_en}{base}".capitalize()
                ur_base = None
            return (sem_id, entry.get("en") or en_base, entry.get("ur") or ur_base, None, None, None)
        if db == 1 and da >= 2:
            base = "uncle" if target_gender == "male" else "aunt"
            base_cap = base.capitalize()
            if da == 2:
                sem_id = f"{side_prefix}{base}"
                en_base = f"{side_word}{base_cap}".strip()
                ur_base = UNCLE_AUNT_UR.get((side, target_gender))
            elif da == 3:
                sem_id = f"{side_prefix}great_{base}"
                en_base = f"{side_word}Great-{base}".strip()
                ur_base = None
            else:
                prefix_id = "great_" * (da - 2)
                prefix_en = "great-" * (da - 2)
                sem_id = f"{side_prefix}{prefix_id}{base}"
                en_base = f"{prefix_en}{side_word}{base}".strip().capitalize()
                ur_base = None
            return (sem_id, entry.get("en") or en_base, entry.get("ur") or ur_base, None, None, side or None)
        if (da >= 2 and db >= 2) or entry.get("degree") is not None:
            degree = entry.get("degree") if entry.get("degree") is not None else (min(da, db) - 1)
            removal = entry.get("removal") if entry.get("removal") is not None else abs(da - db)
            sem_id = f"{side_prefix}cousin_degree_{degree}_removed_{removal}"
            rem_text = _removal_en(removal)
            en_base = f"{side_word}{_ordinal_en(degree)} cousin{' ' + rem_text if rem_text else ''}".strip()
            ur_base = _cousin_ur(degree, removal)
            return (sem_id, entry.get("en") or en_base, entry.get("ur") or ur_base, degree, removal, side or None)

    return None


def normalize_family_entry(entry: dict) -> dict:
    """Attach ``relationship_type``, ``semantic_id``, and structured metadata
    to one engine relationship entry.

    The engine remains authoritative for the label strings; this function is
    a pure deterministic display/indexing layer. Structured kinship facts take
    first priority so semantic identity never depends on English display parsing.
    """
    structured = structured_family_semantic(entry)
    stored_fact_kind = entry.get("stored_fact_kind")
    kind = entry.get("kind") or entry.get("fact_kind")
    if not stored_fact_kind and kind in ("parent_child", "marriage"):
        stored_fact_kind = kind

    derived = entry.get("derived")
    if derived is None:
        if stored_fact_kind in ("parent_child", "marriage", "sibling_group"):
            derived = False
        else:
            derived = True

    if structured is not None:
        type_key, canonical_en, canonical_ur, degree, removal, side = structured
        return {
            "domain": "family",
            "relationship_type": type_key,
            "semantic_id": type_key,
            "label_en": entry.get("en") or canonical_en,
            "label_ur": entry.get("ur") or canonical_ur,
            "side": side if side is not None else entry.get("side"),
            "degree": degree if degree is not None else entry.get("degree"),
            "removal": removal if removal is not None else entry.get("removal"),
            "derived": derived,
            "stored_fact_kind": stored_fact_kind,
            "stored_fact_id": entry.get("stored_fact_id"),
            "kind": entry.get("kind"),
            "role": entry.get("role"),
        }

    # Legacy fallback: parse English text when entry lacks structured metadata
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
        norm_clean = base_en.lower().replace("-", "_")
        slug = re.sub(r"[^a-z0-9]+", "_", norm_clean).strip("_")
        type_key = f"family_{slug or 'unknown'}"
        canonical_en = base_en
    if suffix:
        type_key = f"{type_key}_{suffix}"
    if not canonical_ur and suffix:
        canonical_ur = None

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
        "stored_fact_kind": stored_fact_kind,
        "stored_fact_id": entry.get("stored_fact_id"),
        "kind": entry.get("kind"),
        "role": entry.get("role"),
    }


def normalize_general_entry(
    row,
    *,
    from_person: str,
    label_a_to_b: str | None,
    label_b_to_a: str | None,
) -> dict:
    row_keys = row.keys() if hasattr(row, "keys") else ()
    directionality = row["directionality"]
    row_id = row["id"] if "id" in row_keys else None
    direction_from = row["direction_from"] if "direction_from" in row_keys else None

    if directionality == "directional":
        is_forward = direction_from == from_person
        label = label_a_to_b if is_forward else label_b_to_a
        reverse_label = label_b_to_a if is_forward else label_a_to_b
    else:
        label = label_a_to_b or label_b_to_a
        reverse_label = label

    type_key = row["type"]
    entry = {
        "domain": "general",
        "relationship_type": type_key,
        "semantic_id": f"general_{type_key}",
        "label_en": label,
        "label_ur": None,
        "derived": False,
        "directionality": directionality,
        "reverse_label_en": reverse_label,
        "notes": row["notes"] if "notes" in row_keys else None,
    }
    if row_id is not None:
        entry["id"] = f"general:{row_id}:{from_person}"
        entry["general_relationship_id"] = row_id
        entry["stored_fact_id"] = f"general_relationship:{row_id}"
    if direction_from is not None:
        entry["direction_from"] = direction_from
    return entry
