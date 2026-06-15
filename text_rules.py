from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd
import yaml


@dataclass(frozen=True)
class Candidate:
    category: str
    score: float
    source: str
    reason: str


@dataclass(frozen=True)
class Denial:
    targets: tuple[str, ...]
    rule_id: str
    reason: str


@dataclass(frozen=True)
class LexiconRule:
    rule_id: str
    level: str
    scope: str
    category_candidates: tuple[str, ...]
    target_categories: tuple[str, ...]
    positive_any: tuple[str, ...]
    positive_all: tuple[str, ...]
    positive_regex_any: tuple[str, ...]
    positive_regex_all: tuple[str, ...]
    negative_any: tuple[str, ...]
    negative_regex_any: tuple[str, ...]
    name_positive_any: tuple[str, ...]
    name_negative_any: tuple[str, ...]
    name_positive_regex_any: tuple[str, ...]
    address_positive_any: tuple[str, ...]
    address_negative_any: tuple[str, ...]
    address_positive_regex_any: tuple[str, ...]
    confidence: float
    reason: str


def safe_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def normalize_text(value) -> str:
    text = safe_text(value)
    text = text.replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def compact_text(value) -> str:
    return re.sub(r"\s+", "", normalize_text(value))


def pick_col(df: pd.DataFrame, candidates: Sequence[str], required: bool = True) -> str | None:
    cols = {str(col).strip(): col for col in df.columns}
    for name in candidates:
        if name in cols:
            return cols[name]
    if required:
        raise ValueError(f"找不到列：{', '.join(candidates)}")
    return None


def build_category_lookup(category_names: Sequence[str]) -> dict[str, str]:
    return {compact_text(name): str(name) for name in category_names}


def find_category(lookup: dict[str, str], names: Iterable[str]) -> str | None:
    for name in names:
        key = compact_text(name)
        if key in lookup:
            return lookup[key]
    return None


def _seq(item: dict, key: str) -> tuple[str, ...]:
    value = item.get(key) or []
    if isinstance(value, str):
        return (value,)
    return tuple(str(x) for x in value if str(x))


def load_lexicon(path: str | Path) -> list[LexiconRule]:
    path = Path(path)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    rules = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rules.append(LexiconRule(
            rule_id=str(item.get("id", "")),
            level=str(item.get("level", "candidate_boost")),
            scope=str(item.get("scope", "name")),
            category_candidates=_seq(item, "category_candidates"),
            target_categories=_seq(item, "target_categories"),
            positive_any=_seq(item, "positive_any"),
            positive_all=_seq(item, "positive_all"),
            positive_regex_any=_seq(item, "positive_regex_any"),
            positive_regex_all=_seq(item, "positive_regex_all"),
            negative_any=_seq(item, "negative_any"),
            negative_regex_any=_seq(item, "negative_regex_any"),
            name_positive_any=_seq(item, "name_positive_any"),
            name_negative_any=_seq(item, "name_negative_any"),
            name_positive_regex_any=_seq(item, "name_positive_regex_any"),
            address_positive_any=_seq(item, "address_positive_any"),
            address_negative_any=_seq(item, "address_negative_any"),
            address_positive_regex_any=_seq(item, "address_positive_regex_any"),
            confidence=float(item.get("confidence", 0.75)),
            reason=str(item.get("reason", item.get("id", ""))),
        ))
    return rules


def _contains_any(text: str, words: Iterable[str]) -> bool:
    source = compact_text(text).upper()
    return any(str(word).upper() in source for word in words if str(word))


def _contains_all(text: str, words: Iterable[str]) -> bool:
    source = compact_text(text).upper()
    return all(str(word).upper() in source for word in words if str(word))


def _regex_any(text: str, patterns: Iterable[str]) -> bool:
    source = compact_text(text)
    return any(re.search(pattern, source, flags=re.I) for pattern in patterns if str(pattern))


def _regex_all(text: str, patterns: Iterable[str]) -> bool:
    source = compact_text(text)
    return all(re.search(pattern, source, flags=re.I) for pattern in patterns if str(pattern))


def _scope_text(rule: LexiconRule, name: str, address: str) -> str:
    if rule.scope == "address":
        return address
    if rule.scope == "full":
        return f"{name} {address}"
    return name


def _rule_matches(rule: LexiconRule, name: str, address: str) -> bool:
    scoped = _scope_text(rule, name, address)
    if rule.positive_any and not _contains_any(scoped, rule.positive_any):
        return False
    if rule.positive_all and not _contains_all(scoped, rule.positive_all):
        return False
    if rule.positive_regex_any and not _regex_any(scoped, rule.positive_regex_any):
        return False
    if rule.positive_regex_all and not _regex_all(scoped, rule.positive_regex_all):
        return False
    if rule.negative_any and _contains_any(scoped, rule.negative_any):
        return False
    if rule.negative_regex_any and _regex_any(scoped, rule.negative_regex_any):
        return False
    if rule.name_positive_any and not _contains_any(name, rule.name_positive_any):
        return False
    if rule.name_negative_any and _contains_any(name, rule.name_negative_any):
        return False
    if rule.name_positive_regex_any and not _regex_any(name, rule.name_positive_regex_any):
        return False
    if rule.address_positive_any and not _contains_any(address, rule.address_positive_any):
        return False
    if rule.address_negative_any and _contains_any(address, rule.address_negative_any):
        return False
    if rule.address_positive_regex_any and not _regex_any(address, rule.address_positive_regex_any):
        return False
    return True


def lexicon_candidates(
    rules: Sequence[LexiconRule],
    name: str,
    address: str,
    lookup: dict[str, str],
    levels: Iterable[str],
) -> list[Candidate]:
    level_set = set(levels)
    out = []
    for rule in rules:
        if rule.level not in level_set or not _rule_matches(rule, name, address):
            continue
        for rank, category in enumerate(rule.category_candidates):
            resolved = find_category(lookup, [category])
            if resolved:
                score = max(0.0, min(0.99, rule.confidence - 0.04 * rank))
                out.append(Candidate(resolved, score, f"词典:{rule.level}", f"{rule.reason}:{rule.rule_id}"))
                break
    return sorted(out, key=lambda item: item.score, reverse=True)


def lexicon_denials(rules: Sequence[LexiconRule], name: str, address: str) -> list[Denial]:
    out = []
    for rule in rules:
        if rule.level != "deny_or_demote" or not _rule_matches(rule, name, address):
            continue
        out.append(Denial(tuple(rule.target_categories), rule.rule_id, rule.reason))
    return out


def category_denied(category: str, denials: Sequence[Denial]) -> bool:
    return any(category in denial.targets for denial in denials)


def format_candidates(candidates: Sequence[Candidate]) -> str:
    return " | ".join(f"{c.category}:{c.score:.3f}({c.source})" for c in candidates)


def format_denials(denials: Sequence[Denial]) -> str:
    return " | ".join(f"{d.rule_id}:{','.join(d.targets)}({d.reason})" for d in denials)


ADDRESS_SIGNAL = re.compile(r"(省|市|区|县|街道|镇|乡|社区|村|路|街|巷|号|栋|幢|单元|室|楼|附近|对面|正[东南西北]方向)")


def detect_input_mode(name: str, address: str) -> str:
    name_c = compact_text(name)
    address_c = compact_text(address)
    if address_c:
        return "has_name" if name_c else "address_only"
    if len(name_c) >= 18 and ADDRESS_SIGNAL.search(name_c):
        return "address_only"
    return "has_name" if name_c else "address_only"


def name_anchor_candidates(name: str, mode: str, lookup: dict[str, str]) -> list[Candidate]:
    if mode != "has_name":
        return []
    text = compact_text(name)
    rules: list[tuple[str, Sequence[str], float, str]] = [
        (r"宠物医院|动物医院|宠物诊所", ["宠物医院"], 0.99, "宠物医疗名称锚定"),
        (r"社区卫生服务中心|社区卫生服务站|卫生院|卫生室", ["社区医疗", "综合医院"], 0.98, "基层医疗名称锚定"),
        (r"口腔|牙科", ["牙科诊所", "私人诊所"], 0.98, "口腔牙科名称锚定"),
        (r"眼科|眼视光|视光|视力|护眼|近视|验光", ["专科医院", "体检机构", "私人诊所"], 0.97, "眼科视光名称锚定"),
        (r"心理|精神卫生|心理机构", ["私人诊所", "专科医院"], 0.94, "心理健康名称锚定"),
        (r"医院", ["综合医院"], 0.97, "医院名称锚定"),
        (r"诊所|门诊|医务室", ["私人诊所"], 0.96, "诊所门诊名称锚定"),
        (r"幼儿园|托儿所", ["幼儿园/托儿所"], 0.98, "幼儿园名称锚定"),
        (r"小学|一小$|二小$|三小$|四小$|五小$|六小$|七小$|八小$|九小$", ["小学"], 0.98, "小学名称锚定"),
        (r"职业学校|技工学校|高级技工|中等职业|中专|职高|警校", ["中专/职高/技校", "教育"], 0.96, "职业学校名称锚定"),
        (r"大学|学院|高等专科学校|职业技术学院", ["高等院校"], 0.95, "高校名称锚定"),
        (r"中学|高中|初中|外国语学校|附中|长郡|雅礼|实验学校", ["中学", "教育"], 0.94, "中学名称锚定"),
        (r"居民委员会|村民委员会|居委会|村委会", ["村委会/居委会"], 0.99, "居委会村委会名称锚定"),
        (r"社区公共服务中心|社区服务中心|社区服务站|党群服务中心", ["村委会/居委会", "行政办公大厅"], 0.96, "社区服务机构名称锚定"),
        (r"政务服务中心|便民服务中心|办事大厅|行政审批|不动产登记", ["行政办公大厅", "政府及管理机构"], 0.97, "政务服务名称锚定"),
        (r"协会|商会|学会|联合会|促进会|基金会", ["协会", "社会团体、协会"], 0.96, "社会团体名称锚定"),
        (r"警务站|警务室|执勤点|执勤室|治安岗亭", ["派出所", "公检法机构"], 0.96, "警务执勤名称锚定"),
        (r"发改委|监管局|银保监|金融监督管理|财政厅|公安厅|教育厅|民政厅", ["省级政府机关", "政府及管理机构"], 0.97, "政府监管机构名称锚定"),
        (r"街道办事处|街道办|镇政府|乡政府", ["乡、镇级政府机关", "政府及管理机构"], 0.97, "街道乡镇政府名称锚定"),
    ]
    out = []
    for pattern, names, score, reason in rules:
        if re.search(pattern, text, flags=re.I):
            category = find_category(lookup, names)
            if category:
                out.append(Candidate(category, score, "名称锚定", reason))
    return sorted(out, key=lambda item: item.score, reverse=True)


def strong_rule_candidates(name: str, address: str, lookup: dict[str, str]) -> list[Candidate]:
    text = compact_text(f"{name} {address}")
    rules: list[tuple[str, Sequence[str], float, str]] = [
        (r"彩票|福利彩票|体育彩票|彩票站", ["彩票销售"], 0.98, "彩票关键词"),
        (r"银行|支行|分行|营业部|信用社|农商行", ["金融服务", "ATM/自助银行"], 0.92, "银行网点关键词"),
        (r"邮政|邮局|EMS|揽投部", ["邮局", "物流、快运"], 0.94, "邮政关键词"),
        (r"酒店|宾馆|旅馆|民宿|客栈", ["宾馆、酒店", "旅馆、招待所"], 0.93, "住宿关键词"),
        (r"眼科|眼视光|视光|视力|护眼|近视|验光", ["专科医院", "体检机构", "私人诊所"], 0.93, "眼科视光关键词"),
        (r"药店|药房|大药房", ["药店", "医药及医疗器材零售"], 0.94, "药店关键词"),
        (r"超市|便利店", ["超市", "便利店"], 0.90, "超市便利店关键词"),
        (r"餐厅|饭店|餐馆|粉店|面馆|小吃|烧烤|火锅|食府|手工面|石锅鱼", ["中餐馆", "餐馆", "快餐"], 0.88, "餐饮关键词"),
        (r"图文|打印|复印|快印", ["办公服务"], 0.86, "图文办公关键词"),
        (r"地产|房产|置业|中介|经纪", ["房产中介"], 0.86, "房产中介关键词"),
    ]
    out = []
    for pattern, names, score, reason in rules:
        if re.search(pattern, text, flags=re.I):
            category = find_category(lookup, names)
            if category:
                out.append(Candidate(category, score, "强规则", reason))
    return sorted(out, key=lambda item: item.score, reverse=True)


def fallback_candidate(name: str, address: str, lookup: dict[str, str]) -> Candidate:
    text = compact_text(f"{name} {address}")
    if re.search(r"(小区|家园|花园|佳苑|安置区|公寓|苑|府|城).{0,12}(栋|幢|单元|室|号)", text):
        category = find_category(lookup, ["小区门牌", "居民楼门牌", "住宅楼"])
        if category:
            return Candidate(category, 0.58, "兜底", "住宅小区楼栋门牌结构")
    if re.search(r"(公司|集团|有限公司|厂)", text):
        category = find_category(lookup, ["公司", "厂矿企业", "其他单位"])
        if category:
            return Candidate(category, 0.52, "兜底", "企业词兜底")
    category = find_category(lookup, ["其他服务", "其他单位"])
    return Candidate(category or next(iter(lookup.values())), 0.40, "兜底", "无明确高置信候选")


def risk_keyword_missing(category: str, text: str) -> bool:
    compact = compact_text(text)
    risk_groups = {
        "金融服务": ["银行", "支行", "分行", "营业部", "农商行", "信用社", "ATM", "自助银行"],
        "ATM/自助银行": ["ATM", "自助银行", "银行"],
        "专科医院": ["医院", "门诊", "诊所", "医疗", "口腔", "牙科", "康复", "眼科", "眼视光", "视光", "视力", "心理"],
        "综合医院": ["医院", "卫生院", "医疗"],
        "小学": ["小学", "学校", "一小", "二小", "三小"],
        "中学": ["中学", "高中", "初中", "学校"],
        "高等院校": ["大学", "学院", "高等"],
        "彩票销售": ["彩票"],
        "房产中介": ["地产", "房产", "置业", "中介", "经纪"],
    }
    words = risk_groups.get(category)
    if not words:
        return False
    return not any(word.upper() in compact.upper() for word in words)
