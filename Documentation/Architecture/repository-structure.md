# Repository and local data layout

## Local container

On a development machine, Mosaic may be kept in this two-sibling layout:

    Family Relationships/
    ├── Codebase/
    │   ├── .git/
    │   ├── .github/
    │   ├── App/
    │   ├── Desktop/
    │   ├── Documentation/
    │   ├── Packaging/
    │   ├── Resources/
    │   ├── Scripts/
    │   └── Tests/
    └── Mosaic - Local Private Data/
        ├── Database/
        ├── People/
        ├── Backups/
        ├── Raw/
        ├── Media/                 (when present)
        └── .mosaic-quarantine/    (when required)

Codebase is the Git worktree and the only directory represented by the public
remote. The outer Family Relationships directory is only a local container and
is not a Git repository. Mosaic - Local Private Data is local-only runtime and
user data; it is never a source asset, fixture, package input, or Git path.

## Public clone shape

A clone of the public repository has the contents of Codebase at its root:

    clone/
    ├── .github/
    ├── App/
    ├── Desktop/
    ├── Documentation/
    ├── Packaging/
    ├── Resources/
    ├── Scripts/
    ├── Tests/
    ├── README.md
    ├── HARD_RULES.md
    └── THIRD_PARTY_NOTICES.md

There is no additional Codebase wrapper in a fresh clone. Run development,
test, build, and packaging commands from this repository root.

## Public repository roles

| Path | Role |
| --- | --- |
| App/ | FastAPI backend and React/Vite frontend |
| Desktop/Tauri/ | Tauri desktop shell, capabilities, icons, and sidecar staging |
| Documentation/ | Public architecture, development, planning, and synthetic-test documentation |
| Packaging/ | PyInstaller and desktop-package tooling |
| Resources/ | Public bundled third-party assets |
| Scripts/ | Development launchers, verification tools, and privacy gate |
| Tests/ | Synthetic backend and UI test fixtures and suites |
| .github/ | Public continuous-integration workflows |

## Private Data Root

The active Data Root is selected through DataRootManager's OS-local bootstrap
pointer or an explicit environment override. It is not inferred from the
repository location and its absolute path is not committed.

The manager permits a private root beside Codebase, but rejects the Git
checkout itself, any child of the checkout, and aliases that resolve into it.
This permits the local sibling layout above while preventing paths such as:

    <repository root>/Database/
    <repository root>/People/
    <repository root>/Mosaic - Local Private Data/

The portable runtime payload contains Database, People, Backups, Raw, Media
when present, and operation-owned quarantine when required. A fresh public
clone begins unconfigured and must create, select, or restore a private root.

## Packaging and privacy boundary

Build and packaging tools are rooted in Codebase. Their path guard rejects the
sibling Mosaic - Local Private Data directory before a package can read or
write it. The privacy gate fails on private-root paths, databases, unapproved
screenshots, known production identity signatures, and absolute user-profile
paths. Tests construct disposable synthetic Data Roots outside the checkout.

This split keeps the application clone reproducible while preserving the
user's private Mosaic data locally.
