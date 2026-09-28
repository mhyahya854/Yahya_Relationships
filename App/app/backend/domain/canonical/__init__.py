"""Canonical identity, folder structure, and document templates for Mosaic Phase 11."""

from .ids import (
    compute_initials,
    generate_canonical_person_id,
    generate_unresolved_person_id,
    is_valid_canonical_person_id,
    is_valid_unresolved_person_id,
    normalize_name,
)
from .template import (
    FOLDER_TEMPLATE_DIRECTORIES,
    canonical_facts_filename,
    canonical_journal_filename,
    generate_facts_and_about,
    initialize_person_folder,
    parse_facts_and_about,
)

__all__ = [
    "compute_initials",
    "generate_canonical_person_id",
    "generate_unresolved_person_id",
    "is_valid_canonical_person_id",
    "is_valid_unresolved_person_id",
    "normalize_name",
    "FOLDER_TEMPLATE_DIRECTORIES",
    "canonical_facts_filename",
    "canonical_journal_filename",
    "generate_facts_and_about",
    "initialize_person_folder",
    "parse_facts_and_about",
]
