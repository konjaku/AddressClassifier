from __future__ import annotations
import pandas as pd
from addr.types import Category


def load_catalog(path: str = "categories.xlsx") -> dict[str, Category]:
    df = pd.read_excel(path)
    out: dict[str, Category] = {}
    # categories.xlsx 按 一级→二级→三级 排序。跨级重名(如"金融服务"既二级又三级)
    # 必须保留最深级别(三级>二级>一级),让所有分类输出都是三级分类。
    for _, r in df.iterrows():
        name = str(r.get("分类名称", "")).strip()
        if not name or name == "nan":
            continue
        out[name] = Category(  # 同名时后出现的(更深级别)覆盖先出现的
            name=name,
            level=str(r.get("分类级别", "")).strip(),
            path=str(r.get("向量匹配分类描述", "")).split("层级路径：")[-1].split("。")[0].strip(),
            description=str(r.get("向量匹配分类描述", "")),
        )
    return out
