from addr.tongming import extract_primary, candidates
from addr.dictionaries import load_context

CTX = load_context()

def test_primary_is_rightmost_longest():
    # "综合医院"比子串"医院"更长且同末端,主通名取最长
    assert extract_primary("某某综合医院", CTX.tongming) == "综合医院"

def test_candidates_nonempty_for_known_tongming():
    cands = candidates("某某综合医院", CTX)
    assert any(c.category == "综合医院" for c in cands)

def test_candidates_prefer_exact_name_and_deeper_level():
    # "便利店"在多个零售类的"适用对象"里出现(含一级"批发、零售"),
    # 候选首位应是同名/更深层级的"便利店",而不是更粗的一级类
    cands = candidates("某某便利店", CTX)
    assert cands[0].category == "便利店"
