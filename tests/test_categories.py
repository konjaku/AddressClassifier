from addr.categories import load_catalog


def test_catalog_has_known_categories_with_levels():
    cat = load_catalog("categories.xlsx")
    assert cat["综合医院"].level == "三级分类"
    assert cat["金融服务"].level == "二级分类"
    assert "适用对象" in cat["餐馆"].description
