from addr.dictionaries import load_context

def test_context_merges_auto_and_override():
    ctx = load_context(dict_dir="dict", catalog_path="categories.xlsx")
    # override 把"学校"置空,覆盖 auto
    assert ctx.tongming.get("学校", []) == []
    # auto 里仍有通名
    assert "综合医院" in ctx.catalog
