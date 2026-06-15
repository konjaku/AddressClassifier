from __future__ import annotations
import os
import yaml
from addr.types import Context
from addr.categories import load_catalog


def _load_yaml(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or default


def load_context(dict_dir: str = "dict", catalog_path: str = "categories.xlsx") -> Context:
    auto = _load_yaml(f"{dict_dir}/tongming.auto.yaml", {})
    override = _load_yaml(f"{dict_dir}/tongming.override.yaml", {})
    tongming = dict(auto)
    tongming.update(override)                      # override 覆盖(含置空)
    return Context(
        catalog=load_catalog(catalog_path),
        tongming=tongming,
        modifiers=_load_yaml(f"{dict_dir}/modifiers.yaml", []),
        levels=_load_yaml(f"{dict_dir}/levels.yaml", []),
        gazetteer=_load_yaml(f"{dict_dir}/gazetteer.yaml", {}),
        denylist=_load_yaml(f"{dict_dir}/denylist.yaml", []),
    )
