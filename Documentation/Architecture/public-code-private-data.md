# Public code and private Data Root

The public repository holds the Mosaic application, its schema, and fictional
test fixtures. The user-selected Data Root holds every live database, person
folder, journal, Raw item, media file, backup, export, and source record. All
logical `Database/`, `People/`, `Raw/`, `Media/`, and `Backups/` paths in the
Master Plan are relative to the private Data Root.

On a fresh clone, Mosaic starts `UNCONFIGURED`. Use Existing, Create New, and
Restore are explicit ways to activate a private root. The OS-local bootstrap
pointer or an environment override records the choice. A source checkout,
its parent, its children, and aliases to those paths are rejected as a live
root. Installed application layouts are recognized separately.

The private location is selected by the user. **Mosaic - Local Private Data**
is the human-facing name on this development machine; its absolute location
belongs only in OS-local bootstrap state. Development roots stay outside the
checkout and synced directories. The repository contains no default personal
path. Relocation copies verified runtime payload to an empty destination,
retains the old root, and switches the pointer last.

`Raw/` is untrusted intake. An approved file move atomically claims a file into
`.mosaic-quarantine/raw-moves/<operation-id>/` on the same filesystem. The old
Raw pathname is never a cleanup target. Windows cleanup uses a locked file
handle and handle-bound disposition. On macOS and Linux the claimed source is
retained as `CLEANUP_PENDING`; ordinary backups exclude Raw and quarantine
payloads. A verified, completed retained copy moves with the Data Root during
relocation. Incomplete, unowned, changed, or unsafe quarantine content blocks
relocation for review.

Phase 11 remains frozen. Phase 12 is implemented with final system audit
pending. Phase 13 has not started. Historical public commits still require a
dedicated privacy cleanup; this document describes the sanitized current tip.
