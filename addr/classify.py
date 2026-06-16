from __future__ import annotations
import pandas as pd
from addr.types import Context, Result, Candidate
from addr.normalize import split_fields
from addr.segment import main_entity
from addr.tongming import extract_primary, candidates
from addr.disambiguate import disambiguate, gov_level, match_modifier
from addr.gazetteer import brand_hit
from addr.menpai import menpai_category, dorm_category
from addr.arbitrate import arbitrate

_GOV = {"政府及管理机构", "省级政府机关", "国家级政府机关",
        "地级市级政府机关", "区县级政府机关"}
def classify_one(name: str, address: str, ctx: Context) -> Result:
    name, address = split_fields(name, address)
    full = " ".join(p for p in [name, address] if p)
    entity = main_entity(name) if name else main_entity(address)
    dorm = dorm_category(entity)
    if dorm:   # "宿舍/家属楼"是决定性住宅信号,优先于机构通名
        return _finalize([Candidate(category=dorm, source="门牌", evidence="宿舍/家属楼")],
                         "宿舍/家属楼结构", name, full, address, ctx)
    cands = candidates(entity, ctx)
    primary = extract_primary(entity, ctx.tongming) or ""
    # 修饰词权威优先:即使候选为空(如被禁用的"中心")也能据修饰词判定
    mcat, mwhy = match_modifier(primary, full, ctx.modifiers)
    if mcat:
        chosen = next((c for c in cands if c.category == mcat), None) \
            or Candidate(category=mcat, source="消歧", evidence=primary)
        ordered = [chosen] + [c for c in cands if c.category != mcat]
        why = mwhy
    elif cands:
        cat, why = disambiguate(cands, full, primary, ctx.modifiers)
        # 消歧结果作为最终首选(可能是不在通名候选里的类)
        chosen = next((c for c in cands if c.category == cat), None) \
            or Candidate(category=cat, source="消歧", evidence=primary)
        ordered = [chosen] + [c for c in cands if c.category != cat]
    else:
        brand = brand_hit(name, ctx.gazetteer)
        mp = menpai_category(entity)   # 用去括号后缀的主体,避免分店地址(如"…翡翠华庭店")误判门牌
        if brand:
            ordered = [brand]
            why = f"品牌:{brand.evidence}"
        elif mp:
            ordered = [Candidate(category=mp, source="门牌", evidence="住宅结构")]
            why = "门牌/小区结构"
        else:
            ordered = []
            why = "无通名"
    return _finalize(ordered, why, name, full, address, ctx)

def _finalize(ordered, why, name, full, address, ctx) -> Result:
    res = arbitrate(ordered, name, full, why, ctx.denylist, address)
    # 医院的门诊/科室/咨询室是医院科室,归综合医院(而非独立私人诊所/商务服务)
    if "医院" in name and res.category in {"私人诊所", "法律、商务服务"}:
        res.category, res.reason = "综合医院", "医院科室归综合医院"
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
