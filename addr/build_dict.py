from __future__ import annotations
import os
import re
import yaml
from addr.types import Category

_APPLY = re.compile(r"适用对象：(.+?)(。|$)")
_SPLIT = re.compile(r"[、，,/；;]")


def build_tongming_auto(catalog: dict[str, Category], out_path: str) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}

    def add(term: str, name: str):
        term = term.strip()
        if len(term) < 2:
            return
        index.setdefault(term, [])
        if name not in index[term]:
            index[term].append(name)

    for name, c in catalog.items():
        if c.level != "三级分类":
            continue                             # 只从三级分类生成通名,确保输出全是三级
        add(name, name)                          # 分类名本身
        m = _APPLY.search(c.description)
        if m:
            for term in _SPLIT.split(m.group(1)):
                term = re.sub(r"[等\s]+$", "", term)
                if term:
                    add(term, name)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(index, f, allow_unicode=True, sort_keys=True)
    return index
