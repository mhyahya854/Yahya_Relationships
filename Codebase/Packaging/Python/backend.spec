# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for People Relationships packaged backend sidecar.

Builds a self-contained, single-file backend executable containing FastAPI,
Uvicorn, SQLite schema, canonical kinship engine, and domain services.
Excludes private relationship databases, journals, backups, and test suites.
"""

import sys
from pathlib import Path

# Spec file location: Codebase/Packaging/Python/backend.spec
SPEC_DIR = Path(SPEC).resolve().parent
PACKAGING_DIR = SPEC_DIR.parent
CODEBASE_DIR = PACKAGING_DIR.parent
APP_DIR = CODEBASE_DIR / "App"
BACKEND_DIR = APP_DIR / "app" / "backend"

schema_sql = str(BACKEND_DIR / "schema.sql")

datas = [
    (schema_sql, "app/backend"),
    (schema_sql, "."),
]

hiddenimports = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespans",
    "uvicorn.lifespans.auto",
    "fastapi",
    "fastapi.routing",
    "starlette",
    "starlette.routing",
    "pydantic",
    "sqlite3",
    "json",
    "hashlib",
    "shutil",
    "pathlib",
    "uuid",
    "datetime",
]

excludes = [
    "tkinter",
    "matplotlib",
    "numpy",
    "scipy",
    "pandas",
    "pytest",
    "_pytest",
    "unittest",
    "pdb",
    "distutils",
]

a = Analysis(
    [str(BACKEND_DIR / "main.py")],
    pathex=[str(APP_DIR), str(CODEBASE_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="people-relationships-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
