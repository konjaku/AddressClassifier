from __future__ import annotations
import re

# 楼栋/单元/门牌号 → 具体门牌
_DOORPLATE = re.compile(r"[栋幢]|单元|号楼|\d+\s*室|[A-Za-z]?\d+\s*号|[ABCD]区\d")
# 小区出入口/分期 → 小区(整体,而非具体门牌)
_GATE = re.compile(r"[东南西北]+门|出入口|\d+\s*期")
# 住宅小区/楼盘名 → 小区
_RESIDENTIAL = re.compile(r"小区|花园|家园|佳苑|嘉园|公寓|华庭|名邸|新村|安置")

def menpai_category(text: str) -> str | None:
    """住宅门牌/小区结构兜底:仅在无任何业态通名时调用,且应传入已去括号后缀的主体。
    有楼栋/单元/号 → 小区门牌;小区名或出入口 → 小区;都不是 → None。"""
    if not text:
        return None
    if _DOORPLATE.search(text):
        return "小区门牌"
    if _RESIDENTIAL.search(text) or _GATE.search(text):
        return "小区"
    return None
