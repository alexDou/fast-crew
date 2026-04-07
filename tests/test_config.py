"""Tests for settings loading and derived configuration values."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from src.app.core.config import Settings, settings


def _serialize_env_value(value: object) -> str:
    if isinstance(value, SecretStr):
        return json.dumps(value.get_secret_value())
    if isinstance(value, Enum):
        return json.dumps(value.value)
    if value is None:
        return "None"
    return json.dumps(value)


def _write_settings_env(env_path: Path, overrides: dict[str, object] | None = None) -> None:
    overrides = overrides or {}
    lines: list[str] = []

    for field_name in Settings.model_fields:
        value = overrides.get(field_name, getattr(settings, field_name))
        lines.append(f"{field_name}={_serialize_env_value(value)}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_settings_load_from_env_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    _write_settings_env(
        env_path,
        overrides={
            "CRUD_ADMIN_REDIS_PASSWORD": None,
            "SMTP_HOST": None,
            "EMAIL_FROM_ADDRESS": None,
        },
    )

    loaded_settings = Settings(_env_file=env_path)

    assert loaded_settings.APP_NAME == settings.APP_NAME
    assert loaded_settings.POSTGRES_SYNC_DATABASE_URL == settings.POSTGRES_SYNC_DATABASE_URL
    assert loaded_settings.POSTGRES_ASYNC_DATABASE_URL == settings.POSTGRES_ASYNC_DATABASE_URL
    assert loaded_settings.REDIS_CACHE_URL == settings.REDIS_CACHE_URL
    assert loaded_settings.CRUD_ADMIN_REDIS_PASSWORD is None
    assert loaded_settings.SMTP_HOST is None


def test_settings_require_env_values(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    _write_settings_env(env_path)

    env_lines = [
        line
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if not line.startswith("SECRET_KEY=")
    ]
    env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=env_path)

    assert any(error["loc"] == ("SECRET_KEY",) for error in exc_info.value.errors())
