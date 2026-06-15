from __future__ import annotations
from addr.types import Candidate

def disambiguate(cands: list[Candidate], full_text: str, primary_tongming: str,
                 modifiers: list) -> tuple[str | None, str]:
    if not cands:
        return None, "无候选"
    if len(cands) == 1:
        return cands[0].category, "唯一候选"
    # 修饰词命中是权威覆盖:即使 then 不在通名候选里也采纳
    # (如"X中心"含"防御/应急"→政府及管理机构,而"政府及管理机构"并非"中心"的通名候选)
    for rule in modifiers:
        if rule.get("tongming") != primary_tongming:
            continue
        hit = next((w for w in rule.get("if_any", []) if w in full_text), None)
        if hit:
            return rule["then"], f"修饰词'{hit}'→{rule['then']}"
    # 无消歧命中:返回首候选但标注不确定
    return cands[0].category, "多候选未消歧,取首候选"

def gov_level(full_text: str, levels: list) -> str:
    for rule in levels:
        if any(full_text.startswith(p) or p in full_text[:6] for p in rule.get("prefix_any", [])):
            return rule["level"]
    return ""
