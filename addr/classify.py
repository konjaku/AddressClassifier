from __future__ import annotations
import pandas as pd
from addr.types import Context, Result, Candidate
from addr.normalize import split_fields
from addr.segment import main_entity
from addr.tongming import extract_primary, candidates
from addr.disambiguate import disambiguate, gov_level
from addr.gazetteer import brand_hit
from addr.arbitrate import arbitrate

_GOV = {"政府及管理机构", "省级政府机关", "国家级政府机关",
        "地级市级政府机关", "区县级政府机关"}

def classify_one(name: str, address: str, ctx: Context) -> Result:
    name, address = split_fields(name, address)
    full = " ".join(p for p in [name, address] if p)
    entity = main_entity(name) if name else address
    cands = candidates(entity, ctx)
    primary = extract_primary(entity, ctx.tongming) or ""
    if cands:
        cat, why = disambiguate(cands, full, primary, ctx.modifiers)
        # 消歧结果作为最终首选(可能是修饰词注入的、不在通名候选里的类)
        chosen = next((c for c in cands if c.category == cat), None)
        if chosen is None:
            chosen = Candidate(category=cat, source="消歧", evidence=primary)
        ordered = [chosen] + [c for c in cands if c.category != cat]
    else:
        brand = brand_hit(name, ctx.gazetteer)
        if brand:
            ordered = [brand]
            why = f"品牌:{brand.evidence}"
        else:
            ordered = []
            why = "无通名"
    res = arbitrate(ordered, name, full, why, ctx.denylist, address)
    if res.category in _GOV:
        lvl = gov_level(full, ctx.levels)
        if lvl:
            res.gov_level = lvl
    res.level = ctx.catalog[res.category].level if res.category in ctx.catalog else ""
    return res

def classify_df(df: pd.DataFrame, ctx: Context, name_col, address_col) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        nm = str(r.get(name_col, "")) if name_col else ""
        ad = str(r.get(address_col, "")) if address_col else ""
        res = classify_one(nm, ad, ctx)
        out = r.to_dict()
        out.update({
            "原始名称": nm, "原始地址": ad, "最终标准分类": res.category,
            "分类级别": res.level, "命中通名": res.matched_tongming,
            "候选": res.candidates, "消歧依据": res.disambig,
            "行政级别": res.gov_level, "置信": res.confidence,
            "需复核": "是" if res.review else "否", "理由": res.reason,
        })
        rows.append(out)
    return pd.DataFrame(rows)
