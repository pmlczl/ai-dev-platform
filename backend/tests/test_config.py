"""Tests for the environment driven configuration."""

from __future__ import annotations

from pathlib import Path

from app.core.config import BACKEND_DIR, PROJECT_ROOT, Settings


def test_default_dotenv_targets_are_absolute():
    """The dotenv files must not depend on the current working directory."""

    entries = Settings.model_config["env_file"]

    assert all(Path(entry).is_absolute() for entry in entries)
    assert Path(entries[0]) == PROJECT_ROOT / ".env"
    assert Path(entries[1]) == BACKEND_DIR / ".env"


def test_dotenv_targets_survive_a_directory_change(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    entries = Settings.model_config["env_file"]

    assert Path(entries[0]) == PROJECT_ROOT / ".env"
    assert Path(entries[1]) == BACKEND_DIR / ".env"


def test_repository_root_dotenv_is_loaded(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_NAME", raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text("APP_NAME=Root Dotenv App\n", encoding="utf-8")

    settings = Settings(_env_file=str(dotenv))

    assert settings.app_name == "Root Dotenv App"


def test_backend_dotenv_overrides_the_repository_root_dotenv(tmp_path, monkeypatch):
    """``backend/.env`` is listed last and therefore wins over the root file."""

    monkeypatch.delenv("APP_NAME", raising=False)
    root_dotenv = tmp_path / ".env"
    root_dotenv.write_text("APP_NAME=Root Dotenv App\n", encoding="utf-8")
    backend_dotenv = tmp_path / "backend.env"
    backend_dotenv.write_text("APP_NAME=Backend Dotenv App\n", encoding="utf-8")

    settings = Settings(_env_file=(str(root_dotenv), str(backend_dotenv)))

    assert settings.app_name == "Backend Dotenv App"


def test_missing_dotenv_files_are_ignored(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_NAME", raising=False)
    missing = tmp_path / "absent.env"

    settings = Settings(_env_file=str(missing))

    assert settings.app_name == "AI Dev Platform"
