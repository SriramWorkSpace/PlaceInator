"""Compiles tailored LaTeX to PDF via a bundled Tectonic engine (spec section
5, deferred at M3 -- see docs/architecture.md's milestone status).

Tectonic (github.com/tectonic-typesetting/tectonic) rather than requiring a
system MiKTeX/TeX Live install: a single ~50MB self-contained binary that
fetches missing LaTeX packages on demand from its own bundled snapshot. This
mirrors the OCR/Tesseract precedent's "detect an external tool, degrade
honestly if it's missing" shape (see placeinator.placement.parsing's
OcrUnavailableError), but downloads itself automatically instead of pushing a
multi-GB manual MiKTeX/TeX Live install onto the user first.

Downloaded lazily into Settings.bin_dir on first use, never committed to git
or bundled as a PyInstaller/Tauri resource -- same pattern as the embedding
model in Settings.models_dir (placeinator.matching.vectors), and keeps this
feature's footprint to Python code only, no packaging changes.

Verified manually (2026-08-23): the binary download is quick, but the FIRST
real compile also has to bootstrap Tectonic's own LaTeX format cache (dozens
of individual package files fetched from its resource server) -- observed
taking several minutes on a slow connection. Every compile after that is
near-instant (bootstrapped format is cached in Settings.bin_dir alongside the
binary). Deliberately no app-startup warm-up for this, unlike the embedding
model (placeinator.matching.vectors.warm_up_model): Tectonic is needed only
by the PDF-export endpoint, not nearly every feature, so an unconditional
startup warm-up would cost every integration test that builds the real app
a real network hit for a capability most of them never touch (see
placeinator/app.py's own comment on this). compile_tex_to_pdf's lazy
ensure_tectonic() call is the only place this cost is ever paid.
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from placeinator.settings import get_settings

log = logging.getLogger(__name__)

_TECTONIC_VERSION = "0.17.0"
# The GitHub release tag itself is "tectonic@0.17.0" (Cranko's convention,
# URL-encoded here), not a version-only tag -- verified against the real
# release, not guessed.
_TECTONIC_RELEASE_TAG = "tectonic%400.17.0"
_TECTONIC_WINDOWS_ASSET = f"tectonic-{_TECTONIC_VERSION}-x86_64-pc-windows-msvc.zip"
_TECTONIC_DOWNLOAD_URL = (
    "https://github.com/tectonic-typesetting/tectonic/releases/download/"
    f"{_TECTONIC_RELEASE_TAG}/{_TECTONIC_WINDOWS_ASSET}"
)

# Generous enough to cover a cold first-run format bootstrap (observed
# several minutes on a slow connection); a warm compile finishes in well
# under a second regardless, so this only ever matters once per install.
_COMPILE_TIMEOUT_SECONDS = 600


class PdfCompileError(RuntimeError):
    """Tectonic could not be downloaded, or a .tex source failed to compile.
    Wraps both into one catchable type -- see
    placeinator.matching.vectors.ModelDownloadError for the same shape."""


def _tectonic_binary_name() -> str:
    return "tectonic.exe" if platform.system() == "Windows" else "tectonic"


def _tectonic_path() -> Path:
    return get_settings().bin_dir / _tectonic_binary_name()


def ensure_tectonic() -> Path:
    """Downloads and extracts Tectonic into Settings.bin_dir if it isn't
    already there. Windows-only download URL for now, matching this
    project's current Windows-only packaging (docs/architecture.md)."""
    path = _tectonic_path()
    if path.exists():
        return path

    if platform.system() != "Windows":
        raise PdfCompileError(
            f"no bundled Tectonic download is configured for platform {platform.system()!r}"
        )

    settings = get_settings()
    settings.bin_dir.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "tectonic.zip"
            # A pinned, hardcoded GitHub release URL, not user input.
            urllib.request.urlretrieve(_TECTONIC_DOWNLOAD_URL, zip_path)
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp)
            extracted = Path(tmp) / _tectonic_binary_name()
            if not extracted.exists():
                raise PdfCompileError(
                    f"downloaded archive did not contain {_tectonic_binary_name()}"
                )
            shutil.copy2(extracted, path)
    except PdfCompileError:
        raise
    except Exception as exc:
        raise PdfCompileError(f"could not download Tectonic: {exc}") from exc

    return path


def compile_tex_to_pdf(tex: str) -> bytes:
    """Compiles a .tex source string to PDF bytes. Raises PdfCompileError on
    a download failure or a genuine LaTeX compile error -- Tectonic's own
    stderr is included, since a malformed/hand-edited .tex is a real,
    user-facing failure mode, never silently swallowed."""
    tectonic = ensure_tectonic()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "resume.tex").write_text(tex, encoding="utf-8")

        try:
            result = subprocess.run(
                [str(tectonic), "resume.tex", "--outdir", str(tmp_path), "--untrusted"],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=_COMPILE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise PdfCompileError(
                f"PDF compilation timed out after {_COMPILE_TIMEOUT_SECONDS}s"
            ) from exc

        pdf_path = tmp_path / "resume.pdf"
        if result.returncode != 0 or not pdf_path.exists():
            raise PdfCompileError(
                "tectonic failed to compile the resume "
                f"(exit {result.returncode}): {result.stderr.strip()[-2000:]}"
            )

        return pdf_path.read_bytes()
