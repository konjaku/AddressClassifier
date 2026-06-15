"""
留出测试集生成工具：从分类输出中分层抽样，生成人工标注表。

用法:
  # 1) 先跑分类
  python3 -m addr.cli --input data/input/地址_6000.xlsx --output data/output/留出_6000.xlsx

  # 2) 再生成标注表
  python3 -m eval.create_heldout data/output/留出_6000.xlsx categories.xlsx data/output/留出标注表_6000.xlsx
  python3 -m eval.create_heldout data/output/留出_6000.xlsx categories.xlsx data/output/留出标注表_6000.xlsx --gold 80 --silver 80 --review 40
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def load_full_categories(catalog_path: str) -> list[str]:
    """从 categories.xlsx 提取所有唯一分类名称，供下拉菜单。"""
    df = pd.read_excel(catalog_path)
    cats = df["分类名称"].dropna().unique().tolist()
    return sorted(set(cats))


def stratified_sample(df: pd.DataFrame, tier: str, n: int, random_state: int = 42) -> pd.DataFrame:
    """按分类严格比例分层抽样。大类多抽、小类少抽，反映真实分布。"""
    cat_col = "最终标准分类"
    subset = df[df["置信"] == tier].copy()
    if len(subset) == 0:
        return subset
    if len(subset) <= n:
        return subset

    class_counts = subset[cat_col].value_counts()
    total = len(subset)

    # 严格按比例分配（int floor，无最低保障）
    alloc: dict = {}
    for cat, cnt in class_counts.items():
        alloc[cat] = max(0, int(n * cnt / total))

    # 填补因取整损失的差额：按余数(Fractional part)降序补1
    remainders = sorted(
        [(n * cnt / total - alloc[cat], cat) for cat, cnt in class_counts.items()],
        reverse=True,
    )
    diff = n - sum(alloc.values())
    for _, cat in remainders:
        if diff <= 0:
            break
        if alloc[cat] < class_counts[cat]:
            alloc[cat] += 1
            diff -= 1

    # 抽样
    parts = []
    for cat, k in alloc.items():
        if k <= 0:
            continue
        g = subset[subset[cat_col] == cat]
        k = min(k, len(g))
        if k > 0:
            parts.append(g.sample(k, random_state=random_state))
    result = pd.concat(parts, ignore_index=True)

    if len(result) > n:
        result = result.sample(n, random_state=random_state)
    return result


def build_heldout(
    input_path: str,
    catalog_path: str,
    output_path: str,
    n_gold: int = 80,
    n_silver: int = 80,
    n_review: int = 40,
    random_state: int = 42,
):
    df = pd.read_excel(input_path)
    print(f"读取分类结果: {len(df)} 行")
    print(f"  置信分布: {df['置信'].value_counts().to_dict()}")

    gold = stratified_sample(df, "gold", n_gold, random_state)
    silver = stratified_sample(df, "silver", n_silver, random_state)
    review = stratified_sample(df, "review", n_review, random_state)

    print(f"抽样: gold={len(gold)}, silver={len(silver)}, review={len(review)}")

    if len(gold) > 0:
        print("  gold 分类分布:")
        for cat, cnt in gold["最终标准分类"].value_counts().items():
            print(f"    {cat}: {cnt}")
    if len(silver) > 0:
        print("  silver 分类分布:")
        for cat, cnt in silver["最终标准分类"].value_counts().items():
            print(f"    {cat}: {cnt}")

    combined = pd.concat([gold, silver, review], ignore_index=True)
    combined["_sort_conf"] = combined["置信"].map({"gold": 0, "silver": 1, "review": 2})
    combined = combined.sort_values(["_sort_conf", "最终标准分类"]).reset_index(drop=True)

    # 构建标注表
    label_df = pd.DataFrame({
        "序号": range(1, len(combined) + 1),
        "名称": combined["原始名称"],
        "地址": combined["原始地址"],
        "引擎判定": combined["最终标准分类"],
        "置信": combined["置信"],
        "命中通名": combined["命中通名"],
        "理由": combined["理由"],
        "对?(1/0)": np.nan,
        "正确分类(仅当错时填)": np.nan,
    })

    categories = load_full_categories(catalog_path)

    # 写入 Excel
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        label_df.to_excel(writer, sheet_name="标注", index=False)
        pd.DataFrame({"分类名称": categories}).to_excel(writer, sheet_name="分类清单", index=False)

    # 添加下拉验证
    from openpyxl import load_workbook
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = load_workbook(output_path)
    ws = wb["标注"]

    dv_yn = DataValidation(type="list", formula1='"1,0"', allow_blank=True)
    dv_yn.error = "请填 1(对) 或 0(错)"
    col_yn_letter = "H"
    dv_yn.add(f"{col_yn_letter}2:{col_yn_letter}{len(label_df) + 1}")
    ws.add_data_validation(dv_yn)

    max_cat = len(categories) + 1
    dv_cat = DataValidation(type="list", formula1=f"分类清单!$A$2:$A${max_cat}", allow_blank=True)
    dv_cat.error = "请从分类清单中选择"
    col_cat_letter = "I"
    dv_cat.add(f"{col_cat_letter}2:{col_cat_letter}{len(label_df) + 1}")
    ws.add_data_validation(dv_cat)

    wb.save(output_path)

    print(f"\n✅ 标注表已生成: {output_path}")
    print(f"   共 {len(label_df)} 行 (gold={len(gold)}, silver={len(silver)}, review={len(review)})")
    print(f"   包含两个 sheet: '标注'(待人工填写) + '分类清单'(下拉引用)")


def main():
    parser = argparse.ArgumentParser(description="从分类输出生成留出测试集标注表")
    parser.add_argument("input", help="分类结果 xlsx 路径")
    parser.add_argument("catalog", help="categories.xlsx 路径")
    parser.add_argument("output", help="输出标注表 xlsx 路径")
    parser.add_argument("--gold", type=int, default=80)
    parser.add_argument("--silver", type=int, default=80)
    parser.add_argument("--review", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    for p, label in [(args.input, "输入"), (args.catalog, "分类文件")]:
        if not Path(p).exists():
            print(f"错误: {label}文件不存在: {p}", file=sys.stderr)
            sys.exit(1)

    build_heldout(
        input_path=args.input,
        catalog_path=args.catalog,
        output_path=args.output,
        n_gold=args.gold,
        n_silver=args.silver,
        n_review=args.review,
        random_state=args.seed,
    )


if __name__ == "__main__":
    main()
