# Data Root Architecture

## Overview
The **People Relationships Data Root** represents the single authoritative directory for all persistent user data. The active data root is the project root (`Family Relationships/`) itself.

## Directory Structure
```text
Family Relationships/      # Active data root (project root)
│
├── Database/
│   ├── Main/
│   │   └── family.db      # Canonical SQLite database
│   │
│   ├── People/
│   │   ├── Family/        # Per-person directories containing journal.md
│   │   ├── Friends/
│   │   ├── Colleagues/
│   │   ├── Other/
│   │   └── _archived/     # Archived folders for deleted/removed people
│   │
│   ├── Config/            # Portable data-root configuration
│   ├── Sources/           # Evidence source batches
│   ├── Exports/           # Exported HTML/Markdown reports
│   └── Logs/
│
└── Backups/               # Verifiable snapshot backups
    ├── Manual/
    ├── Automatic/
    └── Safety/            # Pre-Upgrade / Pre-Organization / Pre-Restore / Pre-Repair
```

`DataRootManager` still recognizes the legacy layouts (`data/family.db`, root `family.db`, `people/`, `backups/`, `config/`, `exports/`) as fallbacks when the canonical directories above are absent.

## Bootstrap vs. Portable Config
1. **Bootstrap Config**: Located at OS app data (`~/.config/people-relationships/bootstrap.json` or Windows `%APPDATA%\people-relationships\bootstrap.json`). Contains the pointer `active_root` to the current data directory. The environment variable `PEOPLE_RELATIONSHIPS_ROOT` overrides it.
2. **Portable Config**: Located inside `Database/Config/` of the data root. Contains application settings that move seamlessly with the relationship brain when transferred between drives or machines.

## Disconnected Media & Health Audits
- On startup, the application verifies the active data root path.
- If missing or unreadable (e.g. disconnected USB drive), write operations are halted, and a recovery screen allows retrying, selecting an alternate root, or restoring from a backup.
- Empty blank databases are **NEVER** created silently when a root is unreachable.
