from __future__ import annotations
import argparse
import pandas as pd
from addr.dictionaries import load_context
from addr.classify import classify_df


def _pick(df, names):
    cols = {str(c).strip(): c for c in df.columns}
    for n in names:
        if n in cols:
            return cols[n]
    return None


def run(input_path: str, output_path: str, limit: int = 0) -> None:
    ctx = load_context()
    df = pd.read_excel(input_path)
    if limit:
        df = df.head(limit).copy()
    name_col = _pick(df, ["名称", "POI名称", "名字", "name"])
    addr_col = _pick(df, ["地址", "详细地址", "位置", "address"])
    if name_col is None and addr_col is None:
        name_col = df.columns[0]
    result = classify_df(df, ctx, name_col, addr_col)
    result.to_excel(output_path, index=False)
    n_review = (result["需复核"] == "是").sum()
    print(f"完成:{output_path} 共{len(result)}行,需复核{n_review}行")


def main():
    p = argparse.ArgumentParser(description="通名驱动地址分类器")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()
    run(a.input, a.output, a.limit)


if __name__ == "__main__":
    main()
