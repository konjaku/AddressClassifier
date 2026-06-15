from addr.arbitrate import arbitrate
from addr.types import Candidate

DENY = [{"target": "金融服务", "name_negative_any": ["银行", "支行"],
         "address_any": ["对面", "旁边", "附近"], "positive_any": ["银行"]}]

def test_denylist_demotes():
    # "X路银行对面" 不应判金融服务
    cands = [Candidate("金融服务", "通名", "银行")]
    res = arbitrate(cands, "招商大厦", "银行对面招商大厦", "银行对面", DENY)
    assert res.category != "金融服务"

def test_review_when_no_candidate():
    res = arbitrate([], "", "某某不知名实体", "", [])
    assert res.confidence == "review" and res.review is True
