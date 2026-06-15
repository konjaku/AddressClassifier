from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    name: str
    level: str          # "一级分类"/"二级分类"/"三级分类"
    path: str           # 层级路径
    description: str


@dataclass(frozen=True)
class Candidate:
    category: str
    source: str         # "通名"/"品牌"/"消歧"
    evidence: str       # 命中的词/规则


@dataclass
class Result:
    category: str
    level: str
    confidence: str     # "gold"/"silver"/"review"
    matched_tongming: str
    candidates: str
    disambig: str
    gov_level: str
    review: bool
    reason: str


@dataclass
class Context:
    catalog: dict          # name -> Category
    tongming: dict         # term -> list[str] (候选分类名)
    modifiers: list        # 消歧规则
    levels: list           # 行政级别前缀规则
    gazetteer: dict        # 品牌词 -> 分类名
    denylist: list         # 排斥规则
