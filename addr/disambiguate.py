from __future__ import annotations
from addr.types import Candidate

def match_modifier(primary_tongming: str, full_text: str, modifiers: list) -> tuple[str | None, str]:
    """修饰词权威匹配:命中返回 (分类, 理由),否则 (None, "")。
    即使该分类不在通名候选里也成立(如"X中心"含"防御"→政府及管理机构);
    候选为空时(如被禁用的"中心":[])也能触发,用于把政府类中心从噪声里救出。"""
    for rule in modifiers:
        if rule.get("tongming") != primary_tongming:
            continue
        hit = next((w for w in rule.get("if_any", []) if w in full_text), None)
        if hit:
            return rule["then"], f"修饰词'{hit}'→{rule['then']}"
    return None, ""

def disambiguate(cands: list[Candidate], full_text: str, primary_tongming: str,
                 modifiers: list) -> tuple[str | None, str]:
    if not cands:
        return None, "无候选"
    if len(cands) == 1:
        return cands[0].category, "唯一候选"
    mcat, mwhy = match_modifier(primary_tongming, full_text, modifiers)
    if mcat:
        return mcat, mwhy
    # 无消歧命中:返回首候选但标注不确定
    return cands[0].category, "多候选未消歧,取首候选"

def gov_level(full_text: str, levels: list) -> str:
    # levels 按"最具体在前"排列;取首个命中即最深一级(区县 > 市 > 省 > 国家)
    for rule in levels:
        if any(full_text.startswith(p) or p in full_text[:8] for p in rule.get("prefix_any", [])):
            return rule["level"]
    return ""
