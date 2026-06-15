from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import yaml

from text_rules import compact_text, find_category, normalize_text, risk_keyword_missing


@dataclass(frozen=True)
class Prototype:
    name: str
    description: str
    keywords: tuple[str, ...]
    required_any: tuple[str, ...]
    denied_any: tuple[str, ...]
    map_to: tuple[str, ...]


@dataclass
class MatchResult:
    top1: str
    top1_score: float
    top2: str
    top2_score: float
    selected: str
    selected_score: float
    margin: float
    hit_keywords: str
    denied_keywords: str
    suggested_category: str
    adoption: str
    reason: str


def load_prototypes(path: str | Path) -> list[Prototype]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    out = []
    for name, item in data.items():
        item = item or {}
        out.append(Prototype(
            name=str(name),
            description=str(item.get("description", "")),
            keywords=tuple(str(x) for x in item.get("keywords", []) or []),
            required_any=tuple(str(x) for x in item.get("required_any", []) or []),
            denied_any=tuple(str(x) for x in item.get("denied_any", []) or []),
            map_to=tuple(str(x) for x in item.get("map_to", []) or []),
        ))
    if not out:
        raise ValueError(f"核心类型原型为空：{path}")
    return out


def choose_device(device: str) -> str:
    if device != "auto":
        return device
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


class PrototypeMatcher:
    def __init__(
        self,
        prototypes: Sequence[Prototype],
        model_path: str | Path,
        cache_dir: str | Path,
        device: str = "auto",
        batch_size: int = 8,
        max_seq_length: int = 160,
        no_cache: bool = False,
    ):
        self.prototypes = list(prototypes)
        self.model_path = str(model_path)
        self.cache_dir = Path(cache_dir)
        self.device = choose_device(device)
        self.batch_size = batch_size
        self.max_seq_length = max_seq_length
        self.no_cache = no_cache
        self.model = None
        self.prototype_embeddings: np.ndarray | None = None

    def load(self) -> None:
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(self.model_path, device=self.device)
        self.model.max_seq_length = self.max_seq_length
        self.prototype_embeddings = self._load_or_encode_prototypes()

    def _documents(self) -> list[str]:
        return [
            "。".join([
                f"核心类型：{p.name}",
                f"描述：{p.description}",
                f"关键词：{'、'.join(p.keywords)}",
                f"必须命中：{'、'.join(p.required_any)}",
                f"反例：{'、'.join(p.denied_any)}",
                f"映射分类：{'、'.join(p.map_to)}",
            ])
            for p in self.prototypes
        ]

    def _fingerprint(self) -> str:
        payload = [
            {
                "name": p.name,
                "description": p.description,
                "keywords": list(p.keywords),
                "required_any": list(p.required_any),
                "denied_any": list(p.denied_any),
                "map_to": list(p.map_to),
            }
            for p in self.prototypes
        ]
        return hashlib.md5(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]

    def _encode(self, texts: Sequence[str], prompt_name: str = "") -> np.ndarray:
        assert self.model is not None
        kwargs = {
            "batch_size": self.batch_size,
            "normalize_embeddings": True,
            "show_progress_bar": False,
        }
        if prompt_name:
            kwargs["prompt_name"] = prompt_name
        try:
            emb = self.model.encode(list(texts), **kwargs)
        except (TypeError, ValueError):
            kwargs.pop("prompt_name", None)
            emb = self.model.encode(list(texts), **kwargs)
        return np.asarray(emb, dtype=np.float32)

    def _load_or_encode_prototypes(self) -> np.ndarray:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.cache_dir / f"core_types_{self._fingerprint()}_{len(self.prototypes)}.npy"
        if cache_path.exists() and not self.no_cache:
            return np.load(cache_path).astype(np.float32)
        emb = self._encode(self._documents(), prompt_name="passage")
        if not self.no_cache:
            np.save(cache_path, emb)
        return emb

    def match(self, queries: Sequence[str], top_k: int = 2) -> list[tuple[int, int, float, float, float]]:
        if self.prototype_embeddings is None:
            raise RuntimeError("PrototypeMatcher 尚未 load")
        q = self._encode(queries, prompt_name="query")
        scores = q @ self.prototype_embeddings.T
        scores += self._keyword_boost(queries)
        for idx, proto in enumerate(self.prototypes):
            if proto.name == "纯地址定位链":
                scores[:, idx] -= 0.14
        top_k = min(top_k, len(self.prototypes))
        indices = np.argsort(-scores, axis=1)[:, :top_k]
        out = []
        for row, top in enumerate(indices):
            first = int(top[0])
            second = int(top[1]) if len(top) > 1 else first
            s1 = float(scores[row, first])
            s2 = float(scores[row, second]) if len(top) > 1 else 0.0
            out.append((first, second, s1, s2, s1 - s2))
        return out

    def _keyword_boost(self, queries: Sequence[str]) -> np.ndarray:
        boost = np.zeros((len(queries), len(self.prototypes)), dtype=np.float32)
        for row, query in enumerate(queries):
            text = compact_text(query).upper()
            for col, proto in enumerate(self.prototypes):
                hits = 0
                for key in dict.fromkeys([*proto.required_any, *proto.keywords]):
                    if key and str(key).upper() in text:
                        hits += 1
                if hits:
                    boost[row, col] = min(0.12, hits * 0.045)
        return boost


def should_run_deep(row: pd.Series) -> bool:
    if str(row.get("标签等级", "")) == "review":
        return True
    if str(row.get("结果状态", "")) in {"低置信兜底", "建议人工复核"}:
        return True
    if str(row.get("最终标准分类", "")) in {"其他单位", "其他服务"}:
        return True
    return False


def build_query(row: pd.Series) -> str:
    parts = []
    for col in ["原始名称", "原始地址", "最终标准分类", "候选汇总"]:
        value = normalize_text(row.get(col, ""))
        if value:
            parts.append(f"{col}：{value[-80:]}")
    return "。".join(parts)


def apply_deep_fallback(
    df: pd.DataFrame,
    prototype_path: str | Path,
    model_path: str | Path,
    category_lookup: dict[str, str],
    enabled: bool,
    device: str = "auto",
    batch_size: int = 8,
    max_seq_length: int = 160,
    min_score: float = 0.55,
    min_margin: float = 0.08,
    limit: int = 0,
    no_cache: bool = False,
) -> pd.DataFrame:
    cols = [
        "是否进入深度兜底", "深度兜底Top1核心类型", "深度兜底Top1分数", "深度兜底Top2核心类型",
        "深度兜底Top2分数", "深度兜底分差", "深度兜底最终核心类型", "深度兜底命中关键词",
        "深度兜底反例命中词", "深度兜底建议标准分类", "深度兜底采纳等级", "是否采纳深度兜底",
        "深度兜底不采纳原因",
    ]
    numeric_cols = {"深度兜底Top1分数", "深度兜底Top2分数", "深度兜底分差"}
    for col in cols:
        if col not in df.columns:
            df[col] = np.nan if col in numeric_cols else ""
        elif col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = df[col].astype("object")
    if not enabled:
        df["是否进入深度兜底"] = "否"
        df["是否采纳深度兜底"] = "否"
        return df

    candidates = [idx for idx, row in df.iterrows() if should_run_deep(row)]
    if limit and limit > 0:
        candidates = candidates[:limit]
    if not candidates:
        df["是否进入深度兜底"] = "否"
        df["是否采纳深度兜底"] = "否"
        return df

    prototypes = load_prototypes(prototype_path)
    matcher = PrototypeMatcher(
        prototypes=prototypes,
        model_path=model_path,
        cache_dir=Path(model_path).parent / ".cache",
        device=device,
        batch_size=batch_size,
        max_seq_length=max_seq_length,
        no_cache=no_cache,
    )
    matcher.load()
    print(f"深度兜底模型已加载：device={matcher.device}，待处理={len(candidates)}")

    queries = [build_query(df.loc[idx]) for idx in candidates]
    matches = matcher.match(queries, top_k=2)
    proto_by_name = {p.name: p for p in prototypes}
    for row_idx, (i1, i2, s1, s2, margin) in zip(candidates, matches):
        row = df.loc[row_idx]
        top1, top2 = prototypes[i1], prototypes[i2]
        selected = top1
        selected_score = s1
        if top1.name in {"纯地址定位链", "小区楼盘", "商务楼宇"} and top2.name != top1.name and margin <= 0.12:
            selected = top2
            selected_score = s2
        query_text = compact_text(build_query(row))
        hits = [key for key in [*selected.required_any, *selected.keywords] if key and str(key).upper() in query_text.upper()]
        denied = [key for key in selected.denied_any if key and str(key).upper() in query_text.upper()]
        suggested = find_category(category_lookup, selected.map_to) or ""
        adoption = "reject"
        reject_reason = ""
        if not suggested:
            reject_reason = "核心类型没有可映射标准分类"
        elif str(row.get("标签等级", "")) == "gold":
            reject_reason = "原结果为 gold，不覆盖"
        elif selected.required_any and not hits:
            reject_reason = "缺少 required_any 关键词支持"
        elif denied:
            reject_reason = f"命中反例词：{'、'.join(denied)}"
        elif risk_keyword_missing(suggested, build_query(row)):
            reject_reason = f"风险类别 {suggested} 缺少关键词支持"
        elif selected_score >= min_score and (margin >= min_margin or selected is not top1):
            adoption = "strong_accept"
        elif selected_score >= 0.50 and hits:
            adoption = "weak_suggest"
            reject_reason = "弱建议，未达到强采纳门槛"
        else:
            reject_reason = "分数或分差不足"

        df.at[row_idx, "是否进入深度兜底"] = "是"
        df.at[row_idx, "深度兜底Top1核心类型"] = top1.name
        df.at[row_idx, "深度兜底Top1分数"] = s1
        df.at[row_idx, "深度兜底Top2核心类型"] = top2.name
        df.at[row_idx, "深度兜底Top2分数"] = s2
        df.at[row_idx, "深度兜底分差"] = margin
        df.at[row_idx, "深度兜底最终核心类型"] = selected.name
        df.at[row_idx, "深度兜底命中关键词"] = "、".join(dict.fromkeys(hits))
        df.at[row_idx, "深度兜底反例命中词"] = "、".join(denied)
        df.at[row_idx, "深度兜底建议标准分类"] = suggested
        df.at[row_idx, "深度兜底采纳等级"] = adoption
        df.at[row_idx, "是否采纳深度兜底"] = "是" if adoption == "strong_accept" else "否"
        df.at[row_idx, "深度兜底不采纳原因"] = reject_reason
        if adoption == "strong_accept":
            df.at[row_idx, "最终标准分类"] = suggested
            df.at[row_idx, "最终分数"] = selected_score
            df.at[row_idx, "最终匹配方式"] = "深度兜底"
            df.at[row_idx, "最终置信度"] = "中高"
            df.at[row_idx, "标签等级"] = "silver"
            df.at[row_idx, "结果状态"] = "建议抽检"
            df.at[row_idx, "最终原因"] = f"深度核心类型 {selected.name} 强采纳"

    untouched = set(df.index) - set(candidates)
    if untouched:
        df.loc[list(untouched), "是否进入深度兜底"] = "否"
        df.loc[list(untouched), "是否采纳深度兜底"] = "否"
    return df
