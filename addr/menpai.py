from __future__ import annotations
import re

# 门牌/楼栋/单元/号 等住宅结构标志(强信号)
_DOORPLATE = re.compile(r"[栋幢]|单元|号楼|\d+\s*室|[A-Za-z]?\d+\s*号|[东南西北]+门|[ABCD]区\d")
# 住宅小区/楼盘名(弱信号,仅在无门牌号时用)
_RESIDENTIAL = re.compile(r"小区|花园|家园|佳苑|嘉园|公寓|华庭|名邸|新村|安置")

def menpai_category(text: str) -> str | None:
    """住宅门牌/小区结构兜底:仅在无任何业态通名时调用。
    有楼栋/单元/号 → 小区门牌;否则是住宅小区名 → 小区;都不是 → None。"""
    if not text:
        return None
    if _DOORPLATE.search(text):
        return "小区门牌"
    if _RESIDENTIAL.search(text):
        return "小区"
    return None
