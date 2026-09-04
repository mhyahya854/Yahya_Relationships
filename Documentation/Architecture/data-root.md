# Data Root Architecture

## Overview
The **People Relationships Data Root** represents the single authoritative directory for all persistent user data.

## Directory Structure
```text
People Relationships Data/
│
├── data/
│   └── family.db          # Canonical SQLite database
│
├── people/
│   ├── Family/            # Per-person directories containing journal.md
│   ├── Close Friends/
│   ├── Friends/
│   ├── Colleagues/
│   ├── Mentors/
│   ├── Acquaintances/
│   ├── Other/
│   └── _archived/        # Archived folders for deleted/removed people
│
├── backups/               # Verifiable snapshot backups
├── config/                # Portable data-root configuration
└── exports/               # Exported HTML/Markdown reports
```

## Bootstrap vs. Portable Config
1. **Bootstrap Config**: Located at OS app data (`~/.config/people-relationships/bootstrap.json` or Windows `%APPDATA%\people-relationships\bootstrap.json`). Contains the pointer `active_root` to the current data directory.
2. **Portable Config**: Located inside `Data Root/config/`. Contains application settings that move seamlessly with the relationship brain when transferred between drives or machines.

## Disconnected Media & Health Audits
- On startup, the application verifies the active data root path.
- If missing or unreadable (e.g. disconnected USB drive), write operations are halted, and a recovery screen allows retrying, selecting an alternate root, or restoring from a backup.
- Empty blank databases are **NEVER** created silently when a root is unreachable.
