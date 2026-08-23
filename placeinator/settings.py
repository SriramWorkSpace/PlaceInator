"""Runtime configuration for the PlaceInator sidecar.

Paths resolve to per-user app-data directories so a packaged build never writes
inside its own install location.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from platformdirs import user_data_dir
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "PlaceInator"
APP_AUTHOR = "PlaceInator"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLACEINATOR_", extra="ignore")

    host: str = "127.0.0.1"
    # 0 means "bind an ephemeral port and report it on the handshake line".
    port: int = 0

    # Set by the Rust shell in a packaged build; defaults suit local development.
    data_dir: Path = Path(user_data_dir(APP_NAME, APP_AUTHOR))
    log_level: str = "info"
    dev_mode: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "placeinator.db"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def bin_dir(self) -> Path:
        """Third-party executables downloaded at runtime (e.g. Tectonic,
        see placeinator.latex.compile) -- never bundled in the repo or the
        installer, same reasoning as models_dir for the embedding model."""
        return self.data_dir / "bin"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.models_dir, self.cache_dir, self.bin_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
