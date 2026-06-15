import pytest
from addr.classify import classify_one
from addr.dictionaries import load_context

CTX = load_context()

CASES = [
    ("湖南建设中等职业学校", "中专/职高/技校"),
    ("长沙市雅礼外国语学校", "中学"),
    ("同仁堂国医馆", "私人诊所"),
    ("湖南长沙正尔皮肤病专科", "专科医院"),
    ("长沙南海医院（湖南南海医院管理有限公司）", "综合医院"),
    ("湖南省气象灾害防御技术中心", "政府及管理机构"),
    ("湖南省水利厅", "省级政府机关"),
]

@pytest.mark.parametrize("name,expected", CASES)
def test_known_failures_now_fixed(name, expected):
    res = classify_one(name, "", CTX)
    assert res.category == expected, f"{name} -> {res.category} (期望 {expected}), 理由={res.reason}"
