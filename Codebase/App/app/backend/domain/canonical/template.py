"""Canonical person folder template and facts-and-about file operations.

Governed by Master Plan:
- Folder Template:
  <person-id>/
  ├── <person-id>(facts and about).md
  ├── journal(personal thoughts).md
  ├── Memories(personal history)/
  ├── Conversations (Social Media chats)/
  ├── Documents (Documents about the person)/
  ├── Face (for the apps face detection)/
  └── Profile (Profile Picture)/

- Facts and About fields:
  Explicit Unknown / None values for unrecorded information. No invented data.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

FOLDER_TEMPLATE_DIRECTORIES = (
    "Memories(personal history)",
    "Conversations (Social Media chats)",
    "Documents (Documents about the person)",
    "Face (for the apps face detection)",
    "Profile (Profile Picture)",
)


def canonical_facts_filename(person_id: str) -> str:
    """Return the canonical facts-and-about filename for person_id."""
    return f"{person_id}(facts and about).md"


def canonical_journal_filename() -> str:
    """Return the canonical journal filename."""
    return "journal(personal thoughts).md"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_facts_and_about(
    person_id: str,
    name: str,
    *,
    aliases: Optional[List[str]] = None,
    previous_names: Optional[List[str]] = None,
    birth_year: Optional[int] = None,
    date_of_birth: Optional[str] = None,
    gender: Optional[str] = None,
    phone_numbers: Optional[List[str]] = None,
    email_addresses: Optional[List[str]] = None,
    platform_identities: Optional[List[str]] = None,
    where_we_met: Optional[str] = None,
    when_we_met: Optional[str] = None,
    how_we_met: Optional[str] = None,
    primary_category: str = "Family",
    secondary_relationships: Optional[List[str]] = None,
    groups: Optional[List[str]] = None,
    alternative_group_names: Optional[List[str]] = None,
    contact_status: str = "Active",
    historical_relationship_status: str = "Active",
    identity_link_evidence: Optional[str] = None,
    identity_notes: Optional[str] = None,
    created_at: Optional[str] = None,
    updated_at: Optional[str] = None,
    last_identity_verification: Optional[str] = None,
) -> str:
    """Render deterministic facts-and-about Markdown content for a person."""
    aliases_str = ", ".join(aliases) if aliases else "Unknown"
    prev_names_str = ", ".join(previous_names) if previous_names else "Unknown"

    dob_str = "Unknown"
    if date_of_birth:
        dob_str = str(date_of_birth)
    elif birth_year is not None:
        dob_str = str(birth_year)

    gender_str = gender if gender else "unknown"
    phones_str = ", ".join(phone_numbers) if phone_numbers else "Unknown"
    emails_str = ", ".join(email_addresses) if email_addresses else "Unknown"
    platforms_str = ", ".join(platform_identities) if platform_identities else "Unknown"

    where_str = where_we_met.strip() if where_we_met else "Unknown"
    when_str = when_we_met.strip() if when_we_met else "Unknown"
    how_str = how_we_met.strip() if how_we_met else "Unknown"

    sec_rel_str = ", ".join(secondary_relationships) if secondary_relationships else "None"
    groups_str = ", ".join(groups) if groups else "None"
    alt_groups_str = ", ".join(alternative_group_names) if alternative_group_names else "Unknown"

    c_status = contact_status if contact_status else "Active"
    h_status = historical_relationship_status if historical_relationship_status else "Active"

    evidence_str = identity_link_evidence.strip() if identity_link_evidence else "Unknown"
    notes_str = identity_notes.strip() if identity_notes else "None"

    created = created_at or utc_now_iso()
    updated = updated_at or created
    verified = last_identity_verification or "Unknown"

    lines = [
        f"# Facts and About: {name}",
        "",
        f"- **Canonical ID**: {person_id}",
        f"- **Full Name**: {name}",
        f"- **Aliases / Nicknames**: {aliases_str}",
        f"- **Previous Names**: {prev_names_str}",
        f"- **Date of Birth**: {dob_str}",
        f"- **Gender**: {gender_str}",
        f"- **Current / Old Phone Numbers**: {phones_str}",
        f"- **Current / Old Email Addresses**: {emails_str}",
        f"- **Current / Historical Platform Identities**: {platforms_str}",
        f"- **Where We Met**: {where_str}",
        f"- **When We Met**: {when_str}",
        f"- **How We Met**: {how_str}",
        f"- **Primary Category**: {primary_category}",
        f"- **Secondary / Additional Relationships**: {sec_rel_str}",
        f"- **Groups**: {groups_str}",
        f"- **Alternative Group Names**: {alt_groups_str}",
        f"- **Contact Status**: {c_status}",
        f"- **Historical Relationship Status**: {h_status}",
        f"- **Identity-Link Evidence**: {evidence_str}",
        f"- **Important Identity Notes**: {notes_str}",
        f"- **Created**: {created}",
        f"- **Updated**: {updated}",
        f"- **Last Identity Verification**: {verified}",
        "",
    ]
    return "\n".join(lines)


_FIELD_PATTERN = re.compile(r"^-\s+\*\*([^*]+)\*\*:\s*(.*)$")


def parse_facts_and_about(content: str) -> Dict[str, Any]:
    """Deterministically parse a facts-and-about markdown document."""
    data: Dict[str, Any] = {}
    title_match = re.search(r"^#\s+Facts and About:\s*(.+)$", content, re.MULTILINE)
    if title_match:
        data["title_name"] = title_match.group(1).strip()

    for line in content.splitlines():
        match = _FIELD_PATTERN.match(line.strip())
        if match:
            field_name = match.group(1).strip()
            field_value = match.group(2).strip()
            data[field_name] = field_value

    return data


def initialize_person_folder(
    folder_path: Path,
    person_id: str,
    name: str,
    *,
    primary_category: str = "Family",
    initial_journal_content: Optional[str] = None,
    **facts_kwargs: Any,
) -> None:
    """Initialize a canonical person directory with approved template structure."""
    folder_path.mkdir(parents=True, exist_ok=True)

    for sub_name in FOLDER_TEMPLATE_DIRECTORIES:
        (folder_path / sub_name).mkdir(parents=True, exist_ok=True)

    facts_path = folder_path / canonical_facts_filename(person_id)
    if not facts_path.exists():
        facts_content = generate_facts_and_about(
            person_id,
            name,
            primary_category=primary_category,
            **facts_kwargs,
        )
        facts_path.write_text(facts_content, encoding="utf-8", newline="\n")

    journal_path = folder_path / canonical_journal_filename()
    if not journal_path.exists():
        content = initial_journal_content if initial_journal_content is not None else f"# {name}\n\n"
        journal_path.write_text(content, encoding="utf-8", newline="\n")
