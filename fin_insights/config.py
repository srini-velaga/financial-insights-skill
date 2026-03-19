"""Configuration and data directory resolution."""

import os
from pathlib import Path

# Package root (where profiles/ and config/ ship)
PACKAGE_ROOT = Path(__file__).parent.parent

STATE_DIR = ".fin-insights"
PROFILES_DIR = "profiles"
CONFIG_DIR = "config"
DB_FILENAME = "financial_insights.duckdb"

# File extensions recognized as potential statements
STATEMENT_EXTENSIONS = {".csv", ".pdf"}


def get_data_dir(path: str | None = None) -> Path:
    """Resolve the data directory (where statements live).

    Priority:
      1. Explicit path argument (user-provided or --data-dir CLI flag)
      2. FIN_INSIGHTS_DATA env var
      3. Current working directory
    """
    if path:
        return Path(path).expanduser().resolve()

    env_val = os.environ.get("FIN_INSIGHTS_DATA")
    if env_val:
        return Path(env_val).expanduser().resolve()

    return Path.cwd().resolve()


def get_state_dir(data_dir: Path) -> Path:
    """The .fin-insights directory where DB, profiles, and config live."""
    return data_dir / STATE_DIR


def get_db_path(data_dir: Path) -> Path:
    return get_state_dir(data_dir) / DB_FILENAME


def get_user_profiles_dir(data_dir: Path) -> Path:
    return get_state_dir(data_dir) / PROFILES_DIR


def get_user_config_dir(data_dir: Path) -> Path:
    return get_state_dir(data_dir) / CONFIG_DIR


def get_builtin_profiles_dir() -> Path:
    return PACKAGE_ROOT / PROFILES_DIR


def get_builtin_config_dir() -> Path:
    return PACKAGE_ROOT / CONFIG_DIR


def ensure_state_dir(data_dir: Path) -> Path:
    """Create .fin-insights/ and subdirectories if they don't exist. Returns state dir."""
    state = get_state_dir(data_dir)
    state.mkdir(parents=True, exist_ok=True)
    get_user_profiles_dir(data_dir).mkdir(exist_ok=True)
    get_user_config_dir(data_dir).mkdir(exist_ok=True)
    return state
