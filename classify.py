#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from deep_model import apply_deep_fallback
from retrieval import TextRetriever, decide, load_categories
from text_rules import (
    detect_input_mode,
    fallback_candidate,
    format_candidates,
    format_denials,
    lexicon_candidates,
    lexicon_denials,
    load_lexicon,
    name_anchor_candidates,
    pick_col,
    safe_text,
    strong_rule_candidates,
)


ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="地址名称标准分类器")
    parser.add_argument("--input", default=str(ROOT / "data/input/地址_5000.xlsx"), help="输入 Excel")
    parser.add_argument("--output", default=str(ROOT / "data/output/分类结果.xlsx"), help="输出 Excel")
    parser.add_argument("--categories", default=str(ROOT / "categories.xlsx"), help="标准分类表")
    parser.add_argument("--rules", default=str(ROOT / "rules.yaml"), help="外置 POI 规则词典")
    parser.add_argument("--embedding-model", default=str(ROOT / "models/embedding"), help="embedding 模型目录")
    parser.add_argument("--core-types", default=str(ROOT / "core_types.yaml"), help="核心类型原型")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 行，0 表示全量")
    parser.add_argument("--all-levels", action="store_true", help="使用标准表全部层级；默认只使用三级分类")
    parser.add_argument("--enable-deep", action="store_true", help="启用 embedding 深度兜底")
    parser.add_argument("--deep-device", choices=["auto", "mps", "cpu"], default="auto")
    parser.add_argument("--deep-batch-size", type=int, default=1)
    parser.add_argument("--deep-max-seq-length", type=int, default=160)
    parser.add_argument("--deep-limit", type=int, default=0)
    parser.add_argument("--deep-no-cache", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timings: list[dict] = []
    started = time.perf_counter()

    t0 = time.perf_counter()
    category_df, category_names, lookup = load_categories(args.categories, all_levels=args.all_levels)
    retriever = TextRetriever(category_names, category_df["_doc"].tolist())
    lexicon = load_lexicon(args.rules)
    timings.append({"步骤": "加载分类、规则、检索索引", "耗时秒": round(time.perf_counter() - t0, 3)})

    t0 = time.perf_counter()
    input_df = pd.read_excel(args.input)
    if args.limit and args.limit > 0:
        input_df = input_df.head(args.limit).copy()
    name_col = pick_col(input_df, ["名称", "POI名称", "poi名称", "名字", "name"], required=False)
    address_col = pick_col(input_df, ["地址", "详细地址", "POI地址", "poi地址", "位置", "address"], required=False)
    if name_col is None and address_col is None:
        name_col = input_df.columns[0]
    timings.append({"步骤": "读取输入", "耗时秒": round(time.perf_counter() - t0, 3)})

    rows = []
    t0 = time.perf_counter()
    for idx, row in input_df.iterrows():
        original_name = safe_text(row.get(name_col, "")) if name_col is not None else ""
        original_address = safe_text(row.get(address_col, "")) if address_col is not None else ""
        mode = detect_input_mode(original_name, original_address)
        if mode == "address_only" and not original_address and original_name:
            raw_name = ""
            raw_address = original_name
        else:
            raw_name = original_name
            raw_address = original_address
        full_text = " ".join(part for part in [raw_name, raw_address] if part)

        candidates = []
        denials = lexicon_denials(lexicon, raw_name, raw_address)

        anchors = name_anchor_candidates(raw_name, mode, lookup)
        candidates.extend(anchors)

        if mode == "has_name":
            lex_hard = lexicon_candidates(lexicon, raw_name, raw_address, lookup, ["hard_override"])
            lex_boost = lexicon_candidates(lexicon, raw_name, raw_address, lookup, ["candidate_boost"])
            candidates.extend(lex_hard)
            candidates.extend(lex_boost)
        else:
            lex_hard = []
            lex_boost = []

        strong = strong_rule_candidates(raw_name, raw_address, lookup)
        bm25 = retriever.query(full_text, top_k=5)
        candidates.extend(strong)
        candidates.extend(bm25)
        fallback = fallback_candidate(raw_name, raw_address, lookup)
        decision = decide(candidates, fallback, full_text, denials=denials)

        out = row.to_dict()
        out.update({
            "序号": idx + 1,
            "原始名称": raw_name,
            "原始地址": raw_address,
            "输入模式": mode,
            "词典候选": format_candidates([*lex_hard, *lex_boost]),
            "词典排斥降权": format_denials(denials),
            "名称锚定候选": format_candidates(anchors),
            "强规则候选": format_candidates(strong),
            "检索候选": format_candidates(bm25),
            "候选汇总": format_candidates(candidates),
            "最终标准分类": decision.category,
            "最终分数": decision.score,
            "最终匹配方式": decision.method,
            "最终置信度": decision.confidence,
            "标签等级": decision.grade,
            "结果状态": decision.status,
            "最终原因": decision.reason,
        })
        rows.append(out)
        if (idx + 1) % 500 == 0:
            print(f"已处理 {idx + 1}/{len(input_df)} 行")

    result_df = pd.DataFrame(rows)
    timings.append({"步骤": "规则、检索仲裁", "耗时秒": round(time.perf_counter() - t0, 3)})

    t0 = time.perf_counter()
    result_df = apply_deep_fallback(
        result_df,
        prototype_path=args.core_types,
        model_path=args.embedding_model,
        category_lookup=lookup,
        enabled=args.enable_deep,
        device=args.deep_device,
        batch_size=args.deep_batch_size,
        max_seq_length=args.deep_max_seq_length,
        limit=args.deep_limit,
        no_cache=args.deep_no_cache,
    )
    timings.append({"步骤": "深度兜底", "耗时秒": round(time.perf_counter() - t0, 3)})

    t0 = time.perf_counter()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stats = pd.DataFrame({
        "指标": ["总行数", "gold", "silver", "review", "深度兜底采纳"],
        "数量": [
            len(result_df),
            int((result_df["标签等级"] == "gold").sum()),
            int((result_df["标签等级"] == "silver").sum()),
            int((result_df["标签等级"] == "review").sum()),
            int((result_df.get("是否采纳深度兜底", "") == "是").sum()) if "是否采纳深度兜底" in result_df else 0,
        ],
    })
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        result_df.to_excel(writer, index=False, sheet_name="分类结果")
        stats.to_excel(writer, index=False, sheet_name="分类统计")
        result_df["最终匹配方式"].value_counts().rename_axis("最终匹配方式").reset_index(name="数量").to_excel(
            writer, index=False, sheet_name="方式统计"
        )
        result_df["标签等级"].value_counts().rename_axis("标签等级").reset_index(name="数量").to_excel(
            writer, index=False, sheet_name="标签统计"
        )
        pd.DataFrame(timings + [{"步骤": "总耗时", "耗时秒": round(time.perf_counter() - started, 3)}]).to_excel(
            writer, index=False, sheet_name="耗时统计"
        )
    timings.append({"步骤": "导出 Excel", "耗时秒": round(time.perf_counter() - t0, 3)})

    print(f"完成：{output}")
    print(stats.to_string(index=False))


if __name__ == "__main__":
    main()
