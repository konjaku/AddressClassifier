import json
from eval.run_eval import evaluate

def test_evaluate_on_small_set(tmp_path):
    reg = tmp_path / "reg.jsonl"
    reg.write_text(
        json.dumps({"name": "同仁堂国医馆", "address": "", "label": "私人诊所"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    acc, total, wrong = evaluate(str(reg))
    assert total == 1
    assert acc == 1.0
    assert wrong == []
