from __future__ import annotations
import re

# 轨交站出入口:"X站N出口" / "地铁…出入口"
_TRANSIT = re.compile(r"站\s*[0-9A-Za-z]{0,3}\s*出口|地铁.{0,6}出入口")
# 楼栋/单元/门牌号 → 具体门牌
_DOORPLATE = re.compile(r"[栋幢]|单元|号楼|\d+\s*室|[A-Za-z]?\d+\s*号|[ABCD]区\d")
# 小区出入口/分期 → 小区(整体,而非具体门牌)
_GATE = re.compile(r"[东南西北]+门|出入口|\d+\s*期")
# 住宅小区/楼盘名 → 小区
_RESIDENTIAL = re.compile(r"小区|花园|家园|佳苑|嘉园|公寓|华庭|名邸|新村|安置")

# 宿舍/家属楼:住宅,且"宿舍/家属"须在末端(避免"宿舍区超市"被误判)
_DORM = re.compile(r"(宿舍|家属[区楼]|教工楼|职工楼)\s*[A-Za-z]?\d*\s*[栋幢号]?$")

def dorm_category(text: str) -> str | None:
    """机构宿舍/家属楼 → 住宅楼(决定性住宅信号,应优先于机构通名,如'X医院宿舍4栋')。"""
    return "住宅楼" if text and _DORM.search(text) else None

def menpai_category(text: str) -> str | None:
    """住宅门牌/小区结构兜底:仅在无任何业态通名时调用,且应传入已去括号后缀的主体。
    有楼栋/单元/号 → 小区门牌;小区名或出入口 → 小区;都不是 → None。"""
    if not text:
        return None
    if _TRANSIT.search(text):
        return "地铁站出入口"
    if _DOORPLATE.search(text):
        return "小区门牌"
    if _RESIDENTIAL.search(text) or _GATE.search(text):
        return "小区"
    return None
