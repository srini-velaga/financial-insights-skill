"""Configuration and data directory resolution."""

import os
from pathlib import Path

# Package root (where profiles/ and config/ ship)
PACKAGE_ROOT = Path(__file__).parent.parent

DEFAULT_DATA_DIR = Path.home() / "financial-data"

STATEMENTS_DIR = "statements"
PROFILES_DIR = "profiles"
CONFIG_DIR = "config"
DB_FILENAME = "financial_insights.duckdb"


def get_data_dir(cli_override: str | None = None) -> Path:
    """Resolve the user's data directory.

    Priority: CLI flag > env var > ~/financial-data
    """
    if cli_override:
        return Path(cli_override).expanduser().resolve()

    env_val = os.environ.get("FIN_INSIGHTS_DATA")
    if env_val:
        return Path(env_val).expanduser().resolve()

    return DEFAULT_DATA_DIR.resolve()


def get_db_path(data_dir: Path) -> Path:
    return data_dir / DB_FILENAME


def get_statements_dir(data_dir: Path) -> Path:
    return data_dir / STATEMENTS_DIR


def get_user_profiles_dir(data_dir: Path) -> Path:
    return data_dir / PROFILES_DIR


def get_user_config_dir(data_dir: Path) -> Path:
    return data_dir / CONFIG_DIR


def get_builtin_profiles_dir() -> Path:
    return PACKAGE_ROOT / PROFILES_DIR


def get_builtin_config_dir() -> Path:
    return PACKAGE_ROOT / CONFIG_DIR
