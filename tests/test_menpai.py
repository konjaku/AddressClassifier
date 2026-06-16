from addr.menpai import menpai_category, dorm_category

def test_dorm():
    assert dorm_category("长沙市中心医院宿舍4栋") == "住宅楼"
    assert dorm_category("某某厂家属区") == "住宅楼"
    assert dorm_category("中南大学宿舍区超市") is None   # 末端是超市,不算住宅
    assert dorm_category("湖南广播电视大学教宿舍6栋") is None  # 高校楼栋归高等院校

def test_doorplate_with_building_unit():
    assert menpai_category("松雅小区B20栋B123号") == "小区门牌"
    assert menpai_category("星城社区B区10栋40号") == "小区门牌"

def test_residential_gate():
    assert menpai_category("恒大翡翠华庭北门") == "小区"   # 出入口算小区整体
    assert menpai_category("某某花园") == "小区"           # 纯住宅名

def test_transit_exit():
    assert menpai_category("松雅湖站2出口") == "地铁站出入口"
    assert menpai_category("星沙文体中心站1出口") == "地铁站出入口"

def test_non_residential_returns_none():
    assert menpai_category("绿叶水果") is None
    assert menpai_category("阿布杜新疆烧烤") is None
