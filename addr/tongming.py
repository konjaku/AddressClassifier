from __future__ import annotations
from addr.types import Candidate, Context

_LEVEL_RANK = {"三级分类": 3, "二级分类": 2, "一级分类": 1}

def _matches(text: str, terms) -> list[tuple[int, int, str]]:
    """返回 (起点, 长度, 词):每个出现在 text 中的词典词(取最右出现位置)。"""
    hits = []
    for term in terms:
        if not term:
            continue
        idx = text.rfind(term)
        if idx >= 0:
            hits.append((idx, len(term), term))
    return hits

def extract_primary(text: str, tongming: dict) -> str | None:
    """主通名:最右端者(中文语义中心在右),末端相同则取最长。"""
    hits = _matches(text, tongming.keys())
    if not hits:
        return None
    hits.sort(key=lambda h: (h[0] + h[1], h[1]))
    return hits[-1][2]

def candidates(text: str, ctx: Context) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[str] = set()
    hits = _matches(text, ctx.tongming.keys())
    hits.sort(key=lambda h: (h[0] + h[1], h[1]), reverse=True)   # 偏好靠右的通名
    for _, _, term in hits:
        cats = ctx.tongming.get(term, [])
        # 同一通名内:与通名同名的分类优先,其次层级更深(三级>二级>一级)优先
        cats_sorted = sorted(
            cats,
            key=lambda c: (c == term,
                           _LEVEL_RANK.get(ctx.catalog[c].level, 0) if c in ctx.catalog else 0),
            reverse=True,
        )
        for cat in cats_sorted:
            if cat and cat not in seen:
                seen.add(cat)
                out.append(Candidate(category=cat, source="通名", evidence=term))
    return out
