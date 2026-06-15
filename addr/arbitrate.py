from __future__ import annotations
from addr.types import Candidate, Result

def _denied(category: str, name: str, address: str, full_text: str, denylist: list) -> bool:
    for rule in denylist:
        if rule.get("target") != category:
            continue
        if rule.get("positive_any") and not any(w in full_text for w in rule["positive_any"]):
            continue
        if rule.get("name_negative_any") and any(w in name for w in rule["name_negative_any"]):
            continue  # 名称里有银行等→是本体,不排斥
        if rule.get("address_any") and not any(w in address for w in rule["address_any"]):
            continue
        return True
    return False

def arbitrate(cands: list[Candidate], name: str, full_text: str,
              disambig_reason: str, denylist: list, address: str = "") -> Result:
    kept = [c for c in cands if not _denied(c.category, name, address or full_text, full_text, denylist)]
    if not kept:
        return Result(category="待复核", level="", confidence="review",
                      matched_tongming="", candidates="", disambig=disambig_reason,
                      gov_level="", review=True, reason="无可用候选")
    best = kept[0]
    conf = "gold" if (len(kept) == 1 or "修饰词" in disambig_reason or best.source == "品牌") else "silver"
    return Result(category=best.category, level="", confidence=conf,
                  matched_tongming=best.evidence, candidates=" | ".join(c.category for c in kept),
                  disambig=disambig_reason, gov_level="", review=(conf != "gold"),
                  reason=f"{best.source}:{best.evidence}")
