from __future__ import annotations
import re
from addr.normalize import normalize

# 行政前缀:省/自治区/市/区/县/街道等,允许连续多段
_ADMIN_PREFIX = re.compile(
    r"^((中华人民共和国|[一-龥]{2,8}(省|自治区|特别行政区))?"
    r"([一-龥]{2,8}(市|自治州|地区))?"
    r"([一-龥]{2,8}(区|县|旗))?"
    r"([一-龥]{2,8}(街道|镇|乡))?)"
)
# 末尾括号内的登记/分店信息:（…有限公司）(…店) 等
_PAREN_SUFFIX = re.compile(r"[（(][^）)]*[）)]\s*$")
_BRANCH_SUFFIX = re.compile(r"(NO\.?\s*\d+|第?\d+号馆|连锁)\s*$", re.I)

def main_entity(name: str) -> str:
    s = normalize(name)
    # 反复剥离末尾括号(可能多个)
    prev = None
    while prev != s:
        prev = s
        s = _PAREN_SUFFIX.sub("", s).strip()
        s = _BRANCH_SUFFIX.sub("", s).strip()
    # 剥离开头行政前缀(仅当剥离后仍有实体)
    m = _ADMIN_PREFIX.match(s)
    if m and m.group(0) and len(s) - len(m.group(0)) >= 2:
        s = s[len(m.group(0)):]
    return s.strip()
