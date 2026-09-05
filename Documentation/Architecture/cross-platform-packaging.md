# Cross-Platform Packaging Architecture

This document describes the production packaging architecture for **People Relationships**, ensuring self-contained distribution across Windows, macOS, and Linux without sacrificing data portability, local security, or the single canonical relationship engine.

---

## 1. Architectural Philosophy

People Relationships follows a strict separation of concerns across its stack:

```text
+-------------------------------------------------------------+
|                      User Interface                         |
|           React + TypeScript + Vite (@xyflow/react)          |
+-------------------------------------------------------------+
                              |
                              v  (Webview / IPC)
+-------------------------------------------------------------+
|                     Desktop Container                       |
|           Tauri 2 (Rust) - Window, Tray, Lifecycle           |
+-------------------------------------------------------------+
                              |
                              v  (Managed Process / HTTP 127.0.0.1)
+-------------------------------------------------------------+
|                   Packaged Backend Sidecar                  |
|          FastAPI + Uvicorn + PyInstaller Standalone         |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                 Canonical Kinship Engine                    |
|      domain/family/engine.py (Single source of genealogy)   |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                  Portable Data Root Brain                   |
|       SQLite (Database/Main/family.db) + Markdown Journals   |
+-------------------------------------------------------------+
```

### Key Principles

1. **Shared Application Code**:
   - The React frontend (`Codebase/App/Frontend`) is 100% platform-agnostic.
   - The FastAPI backend service (`Codebase/App/app/backend`) is 100% platform-agnostic.
   - The genealogy/kinship engine (`domain/family/engine.py`) is never duplicated or rewritten for different operating systems.
2. **Platform-Specific Sidecar Binaries**:
   - Python code and dependencies are bundled using PyInstaller on native build runners per target platform.
   - The sidecar is packaged as a standalone executable adhering to Tauri's external binary target-triple naming convention (`people-relationships-backend-<triple>`).
3. **Native Desktop Shell**:
   - Tauri 2 compiles into native system packages (NSIS/MSI for Windows, DMG/.app for macOS, AppImage/.deb for Linux).
   - Desktop manages sidecar process lifecycle (spawning, dynamic port assignment, readiness polling, child tracking, clean termination).
4. **OS-Neutral Data Root**:
   - Relationship data (`Database/Main/family.db`, person journals in `Database/People/`, backups in `Backups/`) is never stored with machine-specific absolute paths.
   - Data roots are 100% portable between Windows, macOS, and Linux.

---

## 2. Directory Structure

```text
Codebase/
├── Packaging/
│   ├── Python/
│   │   └── backend.spec          # PyInstaller spec bundling FastAPI/kinship engine
│   ├── Scripts/
│   │   ├── build_backend.py      # Cross-platform sidecar compilation script
│   │   ├── audit_package.py      # Privacy auditor (verifies zero private data in bundle)
│   │   ├── package.mjs           # Master packaging pipeline orchestrator
│   │   └── test_windows_package.mjs # Automated install/launch/uninstall test
│   └── release/                  # Release manifests and generated package metadata
├── Desktop/
│   └── Tauri/
│       ├── Cargo.toml            # Rust dependencies (tauri, single-instance, dialog)
│       ├── tauri.conf.json       # Tauri 2 configuration & bundle definition
│       ├── src/
│       │   ├── main.rs           # Entry point
│       │   └── lib.rs            # Sidecar lifecycle, dynamic ports, folder picker
│       └── binaries/             # Target-triple sidecar executables
└── App/
    ├── Frontend/                 # React 18 + Vite UI
    └── app/backend/              # FastAPI backend & kinship engine
```

---

## 3. Platform Sidecar Build Architecture

The Python backend is packaged via PyInstaller using `Codebase/Packaging/Python/backend.spec`:

- **Bundled**:
  - FastAPI, Starlette, Uvicorn, Pydantic, SQLite3
  - Core domain kinship engine (`domain/family/engine.py`)
  - Schema definition (`Database/schema.sql`)
  - Asset resolution (`sys._MEIPASS` / frozen mode)
- **Excluded**:
  - All test files (`Tests/`)
  - Live user databases (`family.db`)
  - Personal journals (`Database/People/`)
  - Backups and private source materials
  - Unneeded PyInstaller hooks (Tkinter, matplotlib, scipy, etc.)

### Target Triples

| Target Platform | Target Triple | Executable Name |
|-----------------|---------------|-----------------|
| Windows x64 | `x86_64-pc-windows-msvc` | `people-relationships-backend-x86_64-pc-windows-msvc.exe` |
| macOS Apple Silicon | `aarch64-apple-darwin` | `people-relationships-backend-aarch64-apple-darwin` |
| macOS Intel | `x86_64-apple-darwin` | `people-relationships-backend-x86_64-apple-darwin` |
| Linux x86_64 | `x86_64-unknown-linux-gnu` | `people-relationships-backend-x86_64-unknown-linux-gnu` |

---

## 4. Desktop Shell & Sidecar Lifecycle

In `Codebase/Desktop/Tauri/src/lib.rs`:

1. **Port Negotiation**:
   - Finds an available loopback port starting from 8765.
   - Never conflicts with existing services or forces process termination of third-party apps.
2. **Sidecar Process Spawning**:
   - Resolves sidecar binary from packaged resources or development fallback.
   - Spawns backend with `--host 127.0.0.1 --port <PORT>`.
   - Backend process ID is stored in shared managed state (`Arc<Mutex<Option<Child>>>`).
3. **Readiness Checking**:
   - Desktop window remains hidden (`visible: false`) during launch.
   - Desktop polls `http://127.0.0.1:<PORT>/health` with 50ms intervals up to 15 seconds.
   - Window is revealed only once backend readiness is confirmed (avoiding blank/error screens).
4. **Clean Child Termination**:
   - When the Tauri application window closes or exits, the Rust runtime terminates the tracked child process.
   - No orphan background processes remain running.
5. **Single Instance**:
   - Enforced across all platforms via `tauri-plugin-single-instance`.
   - Second launch attempts focus the existing window and exit immediately without spawning duplicate backends or corrupting databases.

---

## 5. OS-Neutral Data Root & Bootstrap Locations

The application cleanly separates:
1. **Bootstrap configuration** (local to each machine/OS).
2. **Relationship data root** (portable, user-chosen directory).

### Bootstrap Pointers

The active data root pointer is saved in standard OS configuration directories:
- **Windows**: `%APPDATA%\people-relationships\config.json`
- **macOS**: `~/Library/Application Support/people-relationships/config.json`
- **Linux**: `~/.config/people-relationships/config.json` (or `$XDG_CONFIG_HOME/people-relationships/config.json`)

### Portable Data Root

Inside the chosen relationship folder:
```text
<Data Root>/
├── Database/
│   ├── Main/
│   │   └── family.db       # Standard SQLite 3, UTF-8, PRAGMA integrity_check verified
│   ├── People/
│   │   └── <Group>/<PersonID>/journal.md  # Standard UTF-8 Markdown journals
│   ├── Config/
│   │   └── state.json      # UI perspective state
│   └── Exports/
└── Backups/
```

- Path references inside the database and backup manifests use normalized relative paths (`/` forward slashes).
- Folders and person IDs use filesystem-safe alphanumeric characters.
- Backups created on Windows can be restored on macOS or Linux and vice-versa.
