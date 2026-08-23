# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the M0/M1-deferred packaging spike (ADR 0001, ADR 0005).

Onedir, not onefile, per the spike's own requirement -- onefile's runtime
self-extraction to a temp dir adds a second failure mode (antivirus quarantine,
temp-dir permissions) on top of the one this spike exists to isolate: whether
onnxruntime's native libraries get collected at all. Nothing here changes the
Tauri architecture, the ML/matching implementation, or ONNX Runtime -- it only
freezes the existing sidecar as-is.

Explicit collect_all() for every package known (or suspected) to load native
libraries, data files, or plugins dynamically -- PyInstaller's static import
analysis can't see through huggingface_hub's model-file downloads, alembic's
filesystem-scanned migration scripts, SQLAlchemy's entry_point-resolved
dialects, or the google-api namespace packages. Blindly trusting the default
hook set is exactly what this spike exists to NOT do.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

REPO_ROOT = Path(SPECPATH).resolve().parent

datas = []
binaries = []
hiddenimports = []

# Packages with native libraries, dynamic plugin loading, or non-code data
# files that PyInstaller's static analysis cannot see through on its own.
# fastembed + onnxruntime + huggingface_hub + tokenizers are the actual point
# of this spike; the rest are collected for the same underlying reason
# (native libs / entry_point plugins / data files), just for other subsystems
# app.py imports at module level (every api/*.py router, so every one of
# these must import cleanly for the frozen app to even construct).
for pkg in (
    "fastembed",
    "onnxruntime",
    "huggingface_hub",
    "tokenizers",
    "alembic",
    "sqlalchemy",
    "uvicorn",
    "keyring",
    "dateparser",
    "selectolax",
    "pypdfium2",
    "google_auth_oauthlib",
    "googleapiclient",
    "google_auth_httplib2",
):
    try:
        d, b, h = collect_all(pkg)
    except Exception as exc:  # noqa: BLE001 -- report, don't let one missing pkg abort the build
        print(f"[spec] collect_all({pkg!r}) failed: {exc}")
        continue
    datas += d
    binaries += b
    hiddenimports += h

# `google.auth`/`google.oauth2` are namespace packages under the `google`
# umbrella (installed by google-auth, a google-auth-oauthlib dependency) --
# collect_all("google") would sweep in unrelated google-* packages if any
# were ever added, so these are named explicitly instead.
hiddenimports += [
    "google.auth",
    "google.auth.transport.requests",
    "google.oauth2.credentials",
    "google_auth_oauthlib.flow",
    # SQLAlchemy resolves the sqlite dialect via importlib.metadata entry
    # points at runtime, which PyInstaller's static analysis cannot trace.
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
    # pydantic's email extra (pyproject.toml: pydantic[email]).
    "email_validator",
]

# alembic.ini and every migrations/versions/*.py: alembic discovers revision
# scripts by scanning the filesystem at runtime (ScriptDirectory), not via
# any `import` statement PyInstaller's analysis can see -- these would be
# silently dropped otherwise. placeinator/db/migrate.py resolves both
# relative to its own __file__, which PyInstaller sets to a path under
# sys._MEIPASS once frozen, so "." here lands them at the bundle root
# (_internal/ in PyInstaller 6's onedir layout) to match.
datas += [(str(REPO_ROOT / "alembic.ini"), ".")]
datas += [(str(REPO_ROOT / "migrations"), "migrations")]

# taxonomy.json / resources.json: loaded via Path(__file__)-relative code
# (placeinator/skills/taxonomy.py, placeinator/career/resources.py), not
# Python import machinery, so PyInstaller's analysis never sees them either.
datas += [
    (str(REPO_ROOT / "placeinator" / "skills" / "taxonomy.json"), "placeinator/skills"),
    (str(REPO_ROOT / "placeinator" / "skills" / "resources.json"), "placeinator/skills"),
]

a = Analysis(
    [str(REPO_ROOT / "packaging" / "run_sidecar.py")],
    pathex=[str(REPO_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Never let a dev/test-only or explicitly-forbidden (ADR 0002/0005:
        # no LLM, no PyTorch) package sneak into the bundle via some
        # transitive collect_all() sweep.
        "torch",
        "sentence_transformers",
        "transformers",
        "pytest",
        "mypy",
        "ruff",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PlaceInatorBackend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PlaceInatorBackend",
)
