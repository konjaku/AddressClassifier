from addr.normalize import normalize, detect_mode, split_fields

def test_normalize_collapses_and_strips():
    assert normalize("  长沙　市 ") == "长沙 市"

def test_detect_mode():
    assert detect_mode("某某诊所", "长沙市天心区X路1号") == "has_name"
    assert detect_mode("", "长沙市天心区X路1号") == "address_only"
    # 带"市/区"的具名POI(<18字)不能被误判为纯地址
    assert detect_mode("长沙市天心区某某诊所", "") == "has_name"

def test_split_fields_pure_address_in_name_col():
    # 名称列里塞了纯地址(>=18字且含地址信号)→ 搬到地址列
    pure = "湖南省长沙市天心区城南路街道白沙路100号3栋2单元"
    name, addr = split_fields(pure, "")
    assert name == "" and addr == pure
