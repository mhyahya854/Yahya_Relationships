"""Canonical relationship-path extraction.

This module extends — never replaces — the existing kinship implementation in
``build_family.py``. It enumerates the *same* ancestor chains and uses the
*same* record semantics as ``_pair_path_records`` so every returned path
corresponds exactly to a semantic record the engine can produce. Paths are
derived data and are never written anywhere.

The only difference from the engine's ``_pair_path_records`` is that each
deduplicated record remembers one concrete chain pair, which lets us render
an objective node/edge path that "proves" the relationship.
"""

from __future__ import annotations

import hashlib

from . import engine as legacy

VIRTUAL_PREFIX = legacy.VIRTUAL_FULL_ANCESTOR_PREFIX


def _chain_caches(data: dict):
    """Biological parent graph + full-sibling virtual ancestors (same as the
    canonical engine) and an ancestor-chain cache."""
    parents = legacy._biological_parent_index(data)
    legacy._full_sibling_shared_ancestors(data, parents)
    cache: dict = {}
    return parents, cache


def ancestor_chains(person_id: str, data: dict, cache: dict | None = None):
    parents, local_cache = _chain_caches(data)
    cache = cache or local_cache
    return legacy._ancestor_chains(person_id, parents, cache)


def pair_record_paths(data: dict, first: str, second: str, people_index=None):
    """Mirror of ``build_family._pair_path_records`` that keeps one concrete
    chain pair per deduplicated semantic record (plus the union of common
    ancestors that share that record's key)."""
    parents, cache = _chain_caches(data)
    first_chains = legacy._ancestor_chains(first, parents, cache)
    second_chains = legacy._ancestor_chains(second, parents, cache)
    found = {}

    def add(key, value):
        if key not in found:
            found[key] = value

    for chain_a in first_chains:
        set_a = set(chain_a)
        for chain_b in second_chains:
            set_b = set(chain_b)
            common = next((node for node in chain_a if node in set_b), None)
            if common is None:
                continue
            index_a = chain_a.index(common)
            index_b = chain_b.index(common)
            if index_a == 0 and index_b > 0:
                child_id = chain_b[index_b - 1] if index_b >= 1 else None
                add(
                    ("descendant", index_b),
                    {
                        "kind": "descendant",
                        "distance": index_b,
                        "child_id": child_id,
                        "_chain_a": chain_a,
                        "_chain_b": chain_b,
                    },
                )
                continue
            if index_b == 0 and index_a > 0:
                side = ""
                if index_a >= 2 and len(chain_a) > 1:
                    side = legacy._side_of_parent_on_chain(
                        chain_a[1], people_index
                    )
                add(
                    ("ancestor", index_a, side),
                    {
                        "kind": "ancestor",
                        "distance": index_a,
                        "side": side,
                        "_chain_a": chain_a,
                        "_chain_b": chain_b,
                    },
                )
                continue
            if index_a == 0 or index_b == 0:
                continue
            side = ""
            if len(chain_a) > 1:
                side = legacy._side_of_parent_on_chain(chain_a[1], people_index)
            sibling_id = chain_b[1] if index_b >= 2 else None
            parent_first_id = chain_a[1] if index_a >= 2 else None
            key = (index_a, index_b, side, sibling_id, parent_first_id)
            add(
                key,
                {
                    "kind": "collateral",
                    "da": index_a,
                    "db": index_b,
                    "side": side,
                    "sibling_id": sibling_id,
                    "parent_first_id": parent_first_id,
                    "common_ancestor": common,
                    "_chain_a": chain_a,
                    "_chain_b": chain_b,
                },
            )

    # Collect every nearest common ancestor that maps onto the same semantic
    # record (for example both grandparents of a first-cousin path).
    for key, record in found.items():
        ancestors = []
        for chain_a in first_chains:
            for chain_b in second_chains:
                common = next(
                    (node for node in chain_a if node in set(chain_b)), None
                )
                if common is None:
                    continue
                index_a = chain_a.index(common)
                index_b = chain_b.index(common)
                match_key = None
                if index_a == 0 and index_b > 0:
                    match_key = ("descendant", index_b)
                elif index_b == 0 and index_a > 0:
                    side = ""
                    if index_a >= 2 and len(chain_a) > 1:
                        side = legacy._side_of_parent_on_chain(
                            chain_a[1], people_index
                        )
                    match_key = ("ancestor", index_a, side)
                elif index_a > 0 and index_b > 0:
                    side = ""
                    if len(chain_a) > 1:
                        side = legacy._side_of_parent_on_chain(
                            chain_a[1], people_index
                        )
                    sibling_id = chain_b[1] if index_b >= 2 else None
                    parent_first_id = chain_a[1] if index_a >= 2 else None
                    match_key = (
                        index_a,
                        index_b,
                        side,
                        sibling_id,
                        parent_first_id,
                    )
                if match_key == key and common not in ancestors:
                    ancestors.append(common)
        record["common_ancestors"] = ancestors
    return list(found.values())


def concrete_path_nodes(record: dict) -> list[str]:
    """Ordered person/virtual ids from one side of the relationship to the
    other, following the ancestor chains the canonical engine used."""
    chain_a = record["_chain_a"]
    chain_b = record["_chain_b"]
    common = record.get("common_ancestor") or next(
        (node for node in chain_a if node in set(chain_b)), None
    )
    index_a = chain_a.index(common)
    index_b = chain_b.index(common)
    if index_a == 0:
        return list(reversed(chain_b[: index_b + 1]))
    if index_b == 0:
        return list(chain_a[: index_a + 1])
    return list(chain_a[: index_a + 1]) + list(reversed(chain_b[:index_b]))


def canonical_path_id(
    domain: str,
    relationship_type: str,
    node_ids: list[str],
    edge_signature: str,
) -> str:
    payload = "|".join(
        [domain, relationship_type, edge_signature, ">".join(node_ids)]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def is_virtual_node(node_id: str) -> bool:
    return node_id.startswith(VIRTUAL_PREFIX)


def virtual_display_name(node_id: str) -> str:
    if is_virtual_node(node_id):
        return "Shared ancestors (family)"
    return node_id
