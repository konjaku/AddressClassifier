from addr.normalize import normalize, detect_mode, split_fields

def test_normalize_collapses_and_strips():
    assert normalize("  长沙　市 ") == "长沙 市"

def test_detect_mode():
    assert detect_mode("某某诊所", "长沙市天心区X路1号") == "has_name"
    assert detect_mode("", "长沙市天心区X路1号") == "address_only"

def test_split_fields_pure_address_in_name_col():
    name, addr = split_fields("湖南省长沙市天心区X路1号", "")
    assert name == "" and addr == "湖南省长沙市天心区X路1号"
