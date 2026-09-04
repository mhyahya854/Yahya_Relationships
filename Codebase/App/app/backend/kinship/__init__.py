"""Kinship facade.

Everything here delegates to the existing builder so there is exactly one
kinship implementation across the legacy export, the API, Hermes and the UI.
"""

from build_family import (  # noqa: F401
    MAX_KINSHIP_DEPTH,
    _ancestor_chains,
    _audit_derived,
    _biological_parent_index,
    _cousin_en,
    _cousin_ur,
    _derived_focus_entries,
    _full_sibling_shared_ancestors,
    _kinship_terms,
    _pair_path_records,
    _pair_relationship_entries,
    _side_of_parent_on_chain,
    _viewer_pair,
    _viewer_snapshot,
    validate,
)
