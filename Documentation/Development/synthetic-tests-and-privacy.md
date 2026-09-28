# Synthetic tests and privacy gate

`Tests/synthetic_mosaic.py` builds a disposable fictional family in a
temporary canonical Data Root. Backend tests use a temporary OS-local pointer;
the family audit CLI uses the same generator. Tests must not read live
`Database/`, `People/`, or `Backups/` from the source checkout. UI tests and
screenshots must declare synthetic provenance in a sibling `MANIFEST.md` with
the marker `SYNTHETIC_FIXTURE`.

Run the public source gate with:

```text
python Scripts/privacy_gate.py
```

The gate checks the Git index and changed working copies. It refuses private
root paths, databases, uncatalogued screenshots, absolute user-profile paths,
known private identity literals, and known live-data or historical audit hashes.
These signatures are keyed HMACs in
`Scripts/privacy-signatures.json`; the key is kept outside Git in
`MOSAIC_PRIVACY_HMAC_KEY`. CI must receive that key as a protected secret.
Without it the gate fails closed. Do not put the key, a private Data Root, or
unredacted scan logs in a public artifact.

Package builds run the source gate first and then inspect the produced bundle.
The gate and build must pass from a fresh clone with no private data before a
sanitized history candidate can be considered for publication.
