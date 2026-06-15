from addr.disambiguate import disambiguate, gov_level
from addr.types import Candidate

MODIFIERS = [
    {"tongming": "中心", "if_any": ["考试", "测试中心"], "then": "考试中心"},
    {"tongming": "中心", "if_any": ["应急", "管理", "指挥", "防御", "监测"], "then": "政府及管理机构"},
    {"tongming": "医院", "if_any": ["宠物", "动物"], "then": "宠物医院"},
    {"tongming": "医院", "if_any": ["口腔", "眼", "皮肤", "骨", "专科"], "then": "专科医院"},
]
LEVELS = [
    {"prefix_any": ["国家", "全国", "中华人民共和国"], "level": "国家级政府机关"},
    {"prefix_any": ["省", "自治区", "湖南省"], "level": "省级政府机关"},
    {"prefix_any": ["市", "长沙市"], "level": "地级市级政府机关"},
    {"prefix_any": ["区", "县"], "level": "区县级政府机关"},
]

def test_disambiguate_picks_by_modifier():
    cands = [Candidate("考试中心", "通名", "中心"), Candidate("政府及管理机构", "通名", "中心")]
    cat, why = disambiguate(cands, "湖南省气象灾害防御技术中心", "中心", MODIFIERS)
    assert cat == "政府及管理机构"
    assert "防御" in why

def test_gov_level_from_prefix():
    assert gov_level("湖南省水利厅", LEVELS) == "省级政府机关"
