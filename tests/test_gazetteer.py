from addr.gazetteer import brand_hit

GAZ = {"仟吉": "面包房", "富侨": "洗浴中心、SPA、足浴"}

def test_brand_hit():
    c = brand_hit("仟吉西饼解放路店", GAZ)
    assert c is not None and c.category == "面包房"

def test_brand_miss():
    assert brand_hit("某某不知名小店", GAZ) is None
