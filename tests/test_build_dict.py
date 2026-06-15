from addr.build_dict import build_tongming_auto
from addr.categories import load_catalog


def test_build_extracts_terms_from_shiyongduixiang(tmp_path):
    cat = load_catalog("categories.xlsx")
    out = tmp_path / "tongming.auto.yaml"
    index = build_tongming_auto(cat, str(out))
    # "酒楼" 出现在餐馆类"适用对象",应映射到含"餐"的分类
    assert any("餐" in c for c in index.get("酒楼", []))
    assert out.exists()
