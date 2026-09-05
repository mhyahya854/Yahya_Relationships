# Platform Compatibility Matrix

This document tracks the verification and packaging status of **People Relationships** across the target desktop operating systems and architectures.

---

## 1. Target Matrix Status

| Platform | Architecture | Build Type | Status | Verification Level |
|----------|--------------|------------|--------|---------------------|
| **Windows** | `x64` (`x86_64`) | NSIS `.exe` / MSI | **PASS** | Full End-to-End Local Execution (Packaged, Installed, Launched, Health Checked, Smoke Tested, Uninstalled) |
| **macOS** | Apple Silicon (`arm64`) | `.app` + DMG | **CONFIGURED & CI-AUTOMATED** | Packaged via GitHub Actions native runner (`macos-14`), Sidecar build & Tauri bundle workflow configured |
| **macOS** | Intel (`x86_64`) | `.app` + DMG | **CONFIGURED & CI-AUTOMATED** | Packaged via GitHub Actions native runner (`macos-15-intel`), Sidecar build & Tauri bundle workflow configured |
| **Linux** | `x86_64` | AppImage / `.deb` | **CONFIGURED & CI-AUTOMATED** | Packaged via GitHub Actions native runner (`ubuntu-latest`), WebKitGTK & sidecar build workflow configured |

---

## 2. Detailed Platform Breakdown

### Windows x64
- **Host**: Windows 11 x64 (Development & Packaging Host)
- **Artifacts**:
  - `People Relationships_0.5.0_x64-setup.exe` (NSIS Installer)
  - `People Relationships_0.5.0_x64_en-US.msi` (Windows Installer MSI)
  - Sidecar binary: `people-relationships-backend-x86_64-pc-windows-msvc.exe` (PyInstaller)
- **Desktop Shell**: Tauri 2 (Rust MSVC)
- **Manifest**: `Codebase/Packaging/release/release-manifest-windows-x64.json`
- **Verified Operations (Automated via `Packaging/Scripts/test_windows_package.mjs`)**:
  - [x] PyInstaller sidecar compilation (15.10 MB headless)
  - [x] Tauri native bundle generation (NSIS + MSI)
  - [x] Package content privacy audit (zero user databases or journals included)
  - [x] NSIS silent installation to `%LOCALAPPDATA%\Programs\People Relationships`
  - [x] Application launch with packaged sidecar (no terminal window)
  - [x] Dynamic loopback port negotiation (127.0.0.1:8991)
  - [x] Backend `/api/health` readiness check (HTTP 200)
  - [x] First-run data root initialization
  - [x] Database creation and person insertion
  - [x] Clean child process termination (parent watchdog + Tauri exit handlers)
  - [x] Relaunch and data persistence verification
  - [x] Clean uninstallation via silent NSIS uninstaller
  - [x] Verification that user data root survives uninstallation intact

### macOS Apple Silicon (arm64) & Intel (x86_64)
- **Packaging Pipeline**: Configured in `.github/workflows/build-and-package.yml` and `Packaging/Scripts/package.mjs`.
- **Target Triples**:
  - `aarch64-apple-darwin` (Apple Silicon)
  - `x86_64-apple-darwin` (Intel)
- **Bundle Format**: `.app` within `.dmg`.
- **Webview**: Platform-provided WebKit (no bundled Chromium).
- **Bootstrap Config**: `~/Library/Application Support/people-relationships/config.json`.
- **Gatekeeper Note**: Release builds from CI are currently unsigned. On first launch on macOS, users may need to right-click -> Open or approve via System Settings -> Privacy & Security.

### Linux x86_64
- **Packaging Pipeline**: Configured in `.github/workflows/build-and-package.yml`.
- **Target Triple**: `x86_64-unknown-linux-gnu`.
- **Bundle Formats**: AppImage and `.deb`.
- **System Dependencies**: Standard Tauri WebKitGTK runtime (`libwebkit2gtk-4.1-dev` or `libwebkit2gtk-4.0-dev`, `libgtk-3-dev`, `libayatana-appindicator3-dev`).
- **Bootstrap Config**: `~/.config/people-relationships/config.json` (or `$XDG_CONFIG_HOME/people-relationships/config.json`).

---

## 3. Data Portability Verification

Portable data format validation runs in `Codebase/Tests/Backend/test_cross_platform_portability.py`:
- SQLite `family.db` files are OS-neutral and verified via `PRAGMA integrity_check`.
- Markdown journals in `Database/People/` are encoded in strict UTF-8 with universal newline handling.
- Person IDs use filesystem-safe names across Windows, macOS, and Linux filesystems.
- Relative normalized paths (`/`) are used in database manifests and backup files.
