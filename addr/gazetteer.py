from __future__ import annotations
from addr.types import Candidate

def brand_hit(name: str, gazetteer: dict) -> Candidate | None:
    for brand, category in gazetteer.items():
        if brand and brand in name:
            return Candidate(category=category, source="品牌", evidence=brand)
    return None
