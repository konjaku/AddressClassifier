from __future__ import annotations
import pandas as pd
from addr.types import Category


def load_catalog(path: str = "categories.xlsx") -> dict[str, Category]:
    df = pd.read_excel(path)
    out: dict[str, Category] = {}
    for _, r in df.iterrows():
        name = str(r.get("分类名称", "")).strip()
        if not name or name == "nan":
            continue
        if name in out:
            continue
        out[name] = Category(
            name=name,
            level=str(r.get("分类级别", "")).strip(),
            path=str(r.get("向量匹配分类描述", "")).split("层级路径：")[-1].split("。")[0].strip(),
            description=str(r.get("向量匹配分类描述", "")),
        )
    return out
