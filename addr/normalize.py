from __future__ import annotations
import re

_ADDRESS_SIGNAL = re.compile(r"(省|市|区|县|街道|镇|乡|社区|路|街|巷|号|栋|幢|单元|室|楼)")

def normalize(s) -> str:
    if s is None:
        return ""
    s = str(s).replace("　", " ").strip()
    return re.sub(r"\s+", " ", s)

def detect_mode(name: str, address: str) -> str:
    name, address = normalize(name), normalize(address)
    if address:
        return "has_name" if name else "address_only"
    if len(name) >= 8 and _ADDRESS_SIGNAL.search(name):
        return "address_only"
    return "has_name" if name else "address_only"

def split_fields(name: str, address: str) -> tuple[str, str]:
    name, address = normalize(name), normalize(address)
    if not address and detect_mode(name, address) == "address_only":
        return "", name
    return name, address
