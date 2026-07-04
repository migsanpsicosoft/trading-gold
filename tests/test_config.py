"""Tests de humo de la Fase 0: config y logging importan y funcionan."""

from pathlib import Path

from gold_bot.config import PROJECT_ROOT, settings
from gold_bot.utils.log import get_logger


def test_project_root_is_repo_root():
    assert (PROJECT_ROOT / "pyproject.toml").is_file()


def test_data_dirs_under_project():
    assert settings.raw_dir == PROJECT_ROOT / "data" / "raw"
    assert isinstance(settings.data_dir, Path)


def test_seed_is_fixed():
    assert settings.random_seed == 42


def test_logger_smoke():
    log = get_logger("test")
    log.info("evento_de_prueba", clave="valor")
