"""Settings read from the environment once at start-up."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_env: str
    app_version: str
    table_name: str | None

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def load_settings() -> Settings:
    return Settings(
        app_env=os.environ.get("APP_ENV", "local"),
        app_version=os.environ.get("APP_VERSION", "dev"),
        table_name=os.environ.get("TABLE_NAME") or None,
    )
