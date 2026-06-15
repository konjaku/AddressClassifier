from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from text_rules import Candidate, category_denied, compact_text, normalize_text, risk_keyword_missing


@dataclass
class Decision:
    category: str
    score: float
    method: str
    confidence: str
    grade: str
    status: str
    reason: str


def load_categories(path: str | Path, all_levels: bool = False) -> tuple[pd.DataFrame, list[str], dict[str, str]]:
    df = pd.read_excel(path)
    name_col = "分类名称" if "分类名称" in df.columns else df.columns[0]
    if not all_levels and "分类级别" in df.columns:
        level = df["分类级别"].astype(str)
        filtered = df[level.str.contains("三级", na=False)].copy()
        if len(filtered) > 0:
            df = filtered
    df = df.dropna(subset=[name_col]).copy()
    df[name_col] = df[name_col].astype(str).map(normalize_text)
    df = df.drop_duplicates(subset=[name_col], keep="first").reset_index(drop=True)
    desc_col = "向量匹配分类描述" if "向量匹配分类描述" in df.columns else None
    if desc_col:
        df["_doc"] = df[name_col] + "。" + df[desc_col].fillna("").astype(str)
    else:
        df["_doc"] = df[name_col]
    names = df[name_col].tolist()
    return df, names, {compact_text(name): name for name in names}


class TextRetriever:
    def __init__(self, category_names: Sequence[str], documents: Sequence[str]):
        self.category_names = list(category_names)
        self.vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), min_df=1)
        self.matrix = self.vectorizer.fit_transform(list(documents))

    def query(self, text: str, top_k: int = 5) -> list[Candidate]:
        if not compact_text(text):
            return []
        vec = self.vectorizer.transform([text])
        scores = linear_kernel(vec, self.matrix).ravel()
        indices = scores.argsort()[::-1][:top_k]
        out = []
        for idx in indices:
            score = float(scores[idx])
            if score <= 0:
                continue
            out.append(Candidate(
                category=self.category_names[int(idx)],
                score=min(0.92, score),
                source="BM25",
                reason=f"字符ngram检索相似度={score:.3f}",
            ))
        return out


def merge_candidates(candidates: Sequence[Candidate]) -> list[Candidate]:
    merged: dict[str, Candidate] = {}
    for cand in candidates:
        old = merged.get(cand.category)
        if old is None or cand.score > old.score:
            merged[cand.category] = cand
        elif old is not None and cand.source not in old.source:
            merged[cand.category] = Candidate(
                category=old.category,
                score=old.score,
                source=f"{old.source}+{cand.source}",
                reason=f"{old.reason}；{cand.reason}",
            )
    return sorted(merged.values(), key=lambda item: adjusted_score(item), reverse=True)


def adjusted_score(cand: Candidate) -> float:
    bonus = 0.0
    if "名称锚定" in cand.source:
        bonus += 0.20
    if "hard_override" in cand.source:
        bonus += 0.18
    if "强规则" in cand.source:
        bonus += 0.12
    if "candidate_boost" in cand.source:
        bonus += 0.06
    if "BM25" in cand.source:
        bonus += 0.04
    return cand.score + bonus


def decide(
    candidates: Sequence[Candidate],
    fallback: Candidate,
    full_text: str,
    denials=(),
) -> Decision:
    filtered = [
        cand for cand in merge_candidates([*candidates, fallback])
        if not category_denied(cand.category, denials)
    ]
    if not filtered:
        filtered = [fallback]

    best = filtered[0]
    if risk_keyword_missing(best.category, full_text):
        non_risky = [cand for cand in filtered[1:] if not risk_keyword_missing(cand.category, full_text)]
        if non_risky:
            best = non_risky[0]

    confidence = _confidence(best, full_text)
    grade = _grade(confidence, best.category)
    status = _status(confidence, best.category)
    reason = best.reason
    if risk_keyword_missing(best.category, full_text):
        reason += f"；风险类别 {best.category} 缺少关键词支持"
    return Decision(
        category=best.category,
        score=float(best.score),
        method=best.source,
        confidence=confidence,
        grade=grade,
        status=status,
        reason=reason,
    )


def _confidence(cand: Candidate, full_text: str) -> str:
    if cand.category in {"其他单位", "其他服务"}:
        return "低"
    if risk_keyword_missing(cand.category, full_text):
        return "低"
    if "名称锚定" in cand.source or "hard_override" in cand.source:
        return "高" if cand.score >= 0.92 else "中高"
    if "强规则" in cand.source:
        return "高" if cand.score >= 0.92 else "中高"
    if "BM25" in cand.source or "candidate_boost" in cand.source:
        return "中高" if cand.score >= 0.72 else "中"
    if cand.score >= 0.70:
        return "中"
    return "低"


def _grade(confidence: str, category: str) -> str:
    if category in {"其他单位", "其他服务"} or confidence == "低":
        return "review"
    if confidence == "高":
        return "gold"
    return "silver"


def _status(confidence: str, category: str) -> str:
    if category in {"其他单位", "其他服务"} or confidence == "低":
        return "低置信兜底"
    if confidence == "高":
        return "可直接使用"
    return "建议抽检"
