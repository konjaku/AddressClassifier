from addr.menpai import menpai_category

def test_doorplate_with_building_unit():
    assert menpai_category("松雅小区B20栋B123号") == "小区门牌"
    assert menpai_category("星城社区B区10栋40号") == "小区门牌"

def test_residential_gate():
    assert menpai_category("恒大翡翠华庭北门") == "小区门牌"   # 含"北门"
    assert menpai_category("某某花园") == "小区"               # 纯住宅名

def test_non_residential_returns_none():
    assert menpai_category("绿叶水果") is None
    assert menpai_category("阿布杜新疆烧烤") is None
