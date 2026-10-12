"""Loads the three YAML configuration files and applies environment overrides."""
import os
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"

ENV_OVERRIDES = {
    "P2_DB_HOST": ("db", "mysql", "host"),
    "P2_DB_PORT": ("db", "mysql", "port"),
    "P2_DB_NAME": ("db", "mysql", "database"),
    "P2_DB_USER": ("db", "mysql", "user"),
    "P2_INPUT_DIR": ("rules", "paths", "input_dir"),
    "P2_OUTPUT_DIR": ("rules", "paths", "output_dir"),
}


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


def _read_yaml(path):
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ConfigError(f"Configuration file is empty or invalid: {path}")
    return data


def load_config(config_dir=None, overrides=None):
    """Return {'db': ..., 'rules': ..., 'business': ...} with env overrides applied.

    `overrides` is an optional dict of the same shape, used by the offline demo
    and tests to point the framework at other inputs.
    """
    cdir = Path(config_dir) if config_dir else CONFIG_DIR
    cfg = {
        "db": _read_yaml(cdir / "db_config.yaml"),
        "rules": _read_yaml(cdir / "validation_rules.yaml"),
        "business": _read_yaml(cdir / "business_rules.yaml"),
    }
    for env, path in ENV_OVERRIDES.items():
        if os.getenv(env):
            node = cfg
            for part in path[:-1]:
                node = node[part]
            node[path[-1]] = os.getenv(env)
    for section, values in (overrides or {}).items():
        for key, value in values.items():
            if isinstance(value, dict) and isinstance(cfg[section].get(key), dict):
                cfg[section][key].update(value)
            else:
                cfg[section][key] = value

    out = Path(cfg["rules"]["paths"]["output_dir"])
    cfg["rules"]["paths"]["output_dir"] = str(out if out.is_absolute() else PROJECT_ROOT / out)
    return cfg
