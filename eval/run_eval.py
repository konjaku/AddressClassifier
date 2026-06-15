from __future__ import annotations
import json
from addr.dictionaries import load_context
from addr.classify import classify_one

def evaluate(regression_path: str) -> tuple[float, int, list]:
    ctx = load_context()
    total, correct, wrong = 0, 0, []
    with open(regression_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            total += 1
            res = classify_one(row["name"], row.get("address", ""), ctx)
            if res.category == row["label"]:
                correct += 1
            else:
                wrong.append({"name": row["name"], "got": res.category,
                              "want": row["label"], "reason": res.reason})
    acc = correct / total if total else 0.0
    return acc, total, wrong

if __name__ == "__main__":
    import sys
    acc, total, wrong = evaluate(sys.argv[1] if len(sys.argv) > 1 else "eval/regression.jsonl")
    print(f"准确率 {acc:.1%} ({total} 条)")
    for w in wrong:
        print(f"  ✗ {w['name']}: 判={w['got']} 期望={w['want']} ({w['reason']})")
