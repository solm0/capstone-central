from pathlib import Path
from typing import Dict
import importlib
import re


BASE_DIR = Path("./data/static")

_registry: Dict[str, dict] = {}


def parse_version(name: str):
    m = re.search(r"(?:^|[^0-9])v?(\d+)\.(\d+)\.(\d+)$", name)

    if not m:
        return (0, 0, 0)

    return tuple(map(int, m.groups()))


def get_latest_version_path(base: Path):
    versions = [p for p in base.iterdir() if p.is_dir()]

    if not versions:
        raise ValueError(f"No versions for {base}")

    versions.sort(key=lambda p: parse_version(p.name))
    return versions[-1]


def load_language(lang: str):
    if lang in _registry:
        return _registry[lang]

    module = importlib.import_module(f"language_config.{lang}")
    config = module.get_config(BASE_DIR)

    _registry[lang] = config
    return config
