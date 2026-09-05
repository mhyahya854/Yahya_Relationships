#!/usr/bin/env python3
"""Build script for packaging the People Relationships Python backend sidecar.

Uses PyInstaller and backend.spec to produce a platform-specific standalone executable,
naming it according to Tauri's target-triple external binary conventions in
Codebase/Desktop/Tauri/binaries/.
"""

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def get_default_target_triple() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        if machine in ("amd64", "x86_64"):
            return "x86_64-pc-windows-msvc"
        elif machine in ("arm64", "aarch64"):
            return "aarch64-pc-windows-msvc"
    elif system == "darwin":
        if machine in ("arm64", "aarch64"):
            return "aarch64-apple-darwin"
        elif machine in ("x86_64", "amd64"):
            return "x86_64-apple-darwin"
    elif system == "linux":
        if machine in ("x86_64", "amd64"):
            return "x86_64-unknown-linux-gnu"
        elif machine in ("aarch64", "arm64"):
            return "aarch64-unknown-linux-gnu"

    raise RuntimeError(f"Unsupported build platform: {system} {machine}")


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build People Relationships Python Backend Sidecar")
    parser.add_argument("--triple", default=None, help="Target triple (e.g. x86_64-pc-windows-msvc)")
    parser.add_argument("--clean", action="store_true", help="Clean build directories before building")
    args = parser.parse_args()

    triple = args.triple or get_default_target_triple()
    is_windows = "windows" in triple

    scripts_dir = Path(__file__).resolve().parent
    packaging_dir = scripts_dir.parent
    codebase_dir = packaging_dir.parent
    spec_file = packaging_dir / "Python" / "backend.spec"
    dist_dir = packaging_dir / "dist"
    work_dir = packaging_dir / "build"
    tauri_binaries_dir = codebase_dir / "Desktop" / "Tauri" / "binaries"

    print(f"=== Building Python Backend Sidecar for {triple} ===")
    print(f"Spec file: {spec_file}")

    if args.clean:
        if dist_dir.exists():
            shutil.rmtree(dist_dir)
        if work_dir.exists():
            shutil.rmtree(work_dir)

    dist_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    tauri_binaries_dir.mkdir(parents=True, exist_ok=True)

    # Run PyInstaller
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--noconfirm",
        str(spec_file),
    ]

    print(f"Running: {' '.join(cmd)}")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    res = subprocess.run(cmd, cwd=codebase_dir, env=env)
    if res.returncode != 0:
        print(f"PyInstaller build failed with exit code {res.returncode}", file=sys.stderr)
        return res.returncode

    raw_exe_name = "people-relationships-backend.exe" if is_windows else "people-relationships-backend"
    built_exe = dist_dir / raw_exe_name

    if not built_exe.exists():
        print(f"Expected output not found at: {built_exe}", file=sys.stderr)
        return 1

    target_name = f"people-relationships-backend-{triple}.exe" if is_windows else f"people-relationships-backend-{triple}"
    dest_path = tauri_binaries_dir / target_name

    print(f"Copying {built_exe.name} -> {dest_path}")
    shutil.copy2(built_exe, dest_path)

    # Ensure executable permissions on POSIX
    if not is_windows:
        dest_path.chmod(0o755)

    size_mb = dest_path.stat().st_size / (1024 * 1024)
    sha = file_sha256(dest_path)

    print(f"=== Sidecar Build Succeeded ===")
    print(f"Target Binary: {dest_path}")
    print(f"Size: {size_mb:.2f} MB")
    print(f"SHA-256: {sha}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
