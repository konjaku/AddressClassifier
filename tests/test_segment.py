from addr.segment import main_entity

def test_strip_admin_prefix():
    assert main_entity("长沙市天心区某某诊所") == "某某诊所"

def test_strip_registration_paren():
    # 行政前缀(带"市"标记)+ 末尾登记括号都剥离,保留功能实体
    assert main_entity("长沙市南海医院（湖南南海医院管理有限公司）") == "南海医院"

def test_strip_branch_suffix():
    assert main_entity("陈氏面瘫(长沙店)") == "陈氏面瘫"

def test_keep_when_no_prefix():
    assert main_entity("同仁堂国医馆") == "同仁堂国医馆"
