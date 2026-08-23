"""placeinator.latex.compile -- PdfCompileError wrapping for both failure
modes (Tectonic download, real compile), and the happy path. No real
Tectonic binary or network access: subprocess.run and urllib.request are
monkeypatched, mirroring tests/unit/test_vectors_download.py's approach for
the embedding model's own download path.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from placeinator.latex import compile as compile_module
from placeinator.settings import Settings


def _settings_with_bin_dir(data_root: Path) -> Settings:
    return Settings(data_dir=data_root)


def test_ensure_tectonic_returns_existing_path_without_downloading(tmp_path, monkeypatch):
    settings = _settings_with_bin_dir(tmp_path)
    settings.bin_dir.mkdir(parents=True)
    binary = settings.bin_dir / compile_module._tectonic_binary_name()
    binary.write_bytes(b"fake exe")
    monkeypatch.setattr(compile_module, "get_settings", lambda: settings)

    def _boom(*_args, **_kwargs):
        raise AssertionError("should not attempt a download when the binary already exists")

    monkeypatch.setattr(compile_module.urllib.request, "urlretrieve", _boom)

    assert compile_module.ensure_tectonic() == binary


def test_ensure_tectonic_wraps_a_download_failure(tmp_path, monkeypatch):
    settings = _settings_with_bin_dir(tmp_path / "fresh")
    monkeypatch.setattr(compile_module, "get_settings", lambda: settings)

    def _boom(*_args, **_kwargs):
        raise ConnectionError("no route to host")

    monkeypatch.setattr(compile_module.urllib.request, "urlretrieve", _boom)

    with pytest.raises(compile_module.PdfCompileError) as excinfo:
        compile_module.ensure_tectonic()
    assert "no route to host" in str(excinfo.value)


def test_compile_tex_to_pdf_wraps_a_nonzero_exit(monkeypatch):
    monkeypatch.setattr(compile_module, "ensure_tectonic", lambda: Path("fake-tectonic.exe"))

    def _fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="! Undefined control sequence."
        )

    monkeypatch.setattr(compile_module.subprocess, "run", _fake_run)

    with pytest.raises(compile_module.PdfCompileError) as excinfo:
        compile_module.compile_tex_to_pdf(r"\broken")
    assert "Undefined control sequence" in str(excinfo.value)


def test_compile_tex_to_pdf_wraps_a_timeout(monkeypatch):
    monkeypatch.setattr(compile_module, "ensure_tectonic", lambda: Path("fake-tectonic.exe"))

    def _fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="tectonic", timeout=600)

    monkeypatch.setattr(compile_module.subprocess, "run", _fake_run)

    with pytest.raises(compile_module.PdfCompileError, match="timed out"):
        compile_module.compile_tex_to_pdf(r"\documentclass{article}")


def test_compile_tex_to_pdf_returns_bytes_on_success(monkeypatch):
    monkeypatch.setattr(compile_module, "ensure_tectonic", lambda: Path("fake-tectonic.exe"))

    def _fake_run(cmd, cwd, **_kwargs):
        (Path(cwd) / "resume.pdf").write_bytes(b"%PDF-1.5 fake")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(compile_module.subprocess, "run", _fake_run)

    tex = r"\documentclass{article}\begin{document}x\end{document}"
    pdf_bytes = compile_module.compile_tex_to_pdf(tex)
    assert pdf_bytes == b"%PDF-1.5 fake"
