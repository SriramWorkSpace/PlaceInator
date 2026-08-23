"""placeinator.matching.vectors -- ModelDownloadError wrapping and
get_model_download_status()'s three states. No real model needed: _model()
is monkeypatched or its cache is manipulated directly, and
get_model_download_status()'s disk-polling path is tested against a scratch
directory with synthetic files, never the real ~64 MB download.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from placeinator.matching import vectors
from placeinator.settings import Settings


@pytest.fixture(autouse=True)
def _reset_model_cache():
    """_model is a module-level lru_cache shared across the whole process --
    every test here must start and end with it empty, or one test's fake
    model leaks into the next."""
    vectors._model.cache_clear()
    yield
    vectors._model.cache_clear()


def _settings_with_models_dir(models_root: Path) -> Settings:
    # models_dir is a derived property (data_dir / "models"), not a settable
    # field, so point data_dir at a scratch parent and use the real
    # .models_dir it computes -- more faithful than a hand-built stand-in.
    return Settings(data_dir=models_root)


def test_model_download_error_wraps_the_real_exception(monkeypatch):
    def boom(*_args, **_kwargs):
        raise ConnectionError("no route to host")

    monkeypatch.setattr(vectors, "TextEmbedding", boom)

    with pytest.raises(vectors.ModelDownloadError) as excinfo:
        vectors._model()
    assert "no route to host" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, ConnectionError)


def test_status_is_not_ready_when_nothing_on_disk_and_never_loaded(tmp_path, monkeypatch):
    settings = _settings_with_models_dir(tmp_path / "fresh-install")
    monkeypatch.setattr(vectors, "get_settings", lambda: settings)

    status = vectors.get_model_download_status()
    assert status.ready is False
    assert status.downloading is False
    assert status.approx_progress == 0.0


def test_status_reports_downloading_for_a_partial_download(tmp_path, monkeypatch):
    settings = _settings_with_models_dir(tmp_path)
    settings.models_dir.mkdir(parents=True)
    partial_size = vectors._APPROX_MODEL_SIZE_BYTES // 4
    (settings.models_dir / "partial.onnx").write_bytes(b"x" * partial_size)
    monkeypatch.setattr(vectors, "get_settings", lambda: settings)

    status = vectors.get_model_download_status()
    assert status.ready is False
    assert status.downloading is True
    assert 0.2 < status.approx_progress < 0.3


def test_status_reports_ready_when_disk_bytes_already_match_a_complete_download(
    tmp_path, monkeypatch
):
    """A prior run already wrote the full model -- this process just hasn't
    called _model() yet. Must read as ready, not "downloading", since
    loading an already-cached model from disk is fast."""
    settings = _settings_with_models_dir(tmp_path)
    settings.models_dir.mkdir(parents=True)
    (settings.models_dir / "model.onnx").write_bytes(b"x" * vectors._APPROX_MODEL_SIZE_BYTES)
    monkeypatch.setattr(vectors, "get_settings", lambda: settings)

    status = vectors.get_model_download_status()
    assert status.ready is True
    assert status.downloading is False
    assert status.approx_progress == 1.0


def test_status_reports_ready_once_the_model_is_loaded_in_process(monkeypatch):
    """Once _model() has actually been called successfully, that's
    authoritative regardless of what's on disk -- no need to even check."""
    monkeypatch.setattr(vectors, "TextEmbedding", lambda **_kwargs: object())

    vectors._model()
    status = vectors.get_model_download_status()

    assert status.ready is True
    assert status.downloading is False
    assert status.approx_progress == 1.0
