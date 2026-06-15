# 通名驱动地址分类器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用通名(中心词)驱动的确定性规则引擎重做地址/POI 分类器,离线纯传统、完全可解释,目标正确率 ~90%。

**Architecture:** 名字先规范化→剥离行政前缀与登记后缀定位主体→抽取最右通名→映射候选类→修饰词消歧+行政级别判定→优先级裁决→置信分层。词典基础部分从 `categories.xlsx` 的「适用对象」描述自动生成,人工只维护少量覆盖/消歧/品牌/排斥文件。无真值集,靠抽查纠错沉淀回归集。

**Tech Stack:** Python 3.11, pandas, openpyxl, PyYAML, pytest。**不使用** sklearn/torch/sentence-transformers。

---

## 文件结构与接口(先锁定,后续任务复用)

新代码全部在包 `addr/` 下;旧文件(`classify.py`/`text_rules.py`/`retrieval.py`/`deep_model.py`)保留到最后清理。

```
addr/
  categories.py     load_catalog() -> dict[str, Category]
  types.py          Candidate, Result, Context 数据类
  normalize.py      normalize(), detect_mode(), split_fields()
  segment.py        main_entity()
  build_dict.py     build_tongming_auto()  # 离线构建工具
  dictionaries.py   load_context() 合并所有词典 -> Context
  tongming.py       extract_primary(), candidates()
  disambiguate.py   disambiguate(), gov_level()
  gazetteer.py      brand_hit()
  arbitrate.py      arbitrate()
  classify.py       classify_one(), classify_df()
  cli.py            main()  # Excel 读写 + 解释列
dict/
  tongming.auto.yaml      (build_dict 生成)
  tongming.override.yaml  modifiers.yaml  levels.yaml  gazetteer.yaml  denylist.yaml
eval/
  run_eval.py             regression.jsonl  unknown_tongming.log
tests/
  test_*.py
```

**核心数据类型(Task 2 定义,全程复用):**

```python
@dataclass(frozen=True)
class Category:
    name: str
    level: str          # "一级分类"/"二级分类"/"三级分类"
    path: str           # 层级路径
    description: str

@dataclass(frozen=True)
class Candidate:
    category: str
    source: str         # "通名"/"品牌"/"消歧"
    evidence: str       # 命中的词/规则

@dataclass
class Result:
    category: str
    level: str
    confidence: str     # "gold"/"silver"/"review"
    matched_tongming: str
    candidates: str
    disambig: str
    gov_level: str
    review: bool
    reason: str

@dataclass
class Context:
    catalog: dict          # name -> Category
    tongming: dict         # term -> list[str] (候选分类名)
    modifiers: list        # 消歧规则
    levels: list           # 行政级别前缀规则
    gazetteer: dict        # 品牌词 -> 分类名
    denylist: list         # 排斥规则
```

---

## Task 1: 项目脚手架

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `addr/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: 写 requirements.txt**

```text
pandas
openpyxl
PyYAML
pytest
```

- [ ] **Step 2: 写 pytest.ini**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 3: 建空包文件**

`addr/__init__.py` 和 `tests/__init__.py` 写入单行注释 `# package`。

- [ ] **Step 4: 安装依赖并确认 pytest 可运行**

Run: `pip install -r requirements.txt && pytest -q`
Expected: `no tests ran`(无报错)

- [ ] **Step 5: Commit**

```bash
git add requirements.txt pytest.ini addr/__init__.py tests/__init__.py
git commit -m "chore: scaffold addr package and pytest"
```

---

## Task 2: 分类目录与数据类型

**Files:**
- Create: `addr/types.py`, `addr/categories.py`, `tests/test_categories.py`

- [ ] **Step 1: 写 addr/types.py(上面"核心数据类型"全部内容)**

把上节四个 dataclass 原样写入 `addr/types.py`,顶部 `from __future__ import annotations` 和 `from dataclasses import dataclass`。

- [ ] **Step 2: 写失败测试 tests/test_categories.py**

```python
from addr.categories import load_catalog

def test_catalog_has_known_categories_with_levels():
    cat = load_catalog("categories.xlsx")
    assert cat["综合医院"].level == "三级分类"
    assert cat["金融服务"].level == "二级分类"
    assert "适用对象" in cat["餐馆"].description
```

- [ ] **Step 3: 运行确认失败**

Run: `pytest tests/test_categories.py -q`
Expected: FAIL(`ModuleNotFoundError: addr.categories`)

- [ ] **Step 4: 写 addr/categories.py**

```python
from __future__ import annotations
import pandas as pd
from addr.types import Category

def load_catalog(path: str = "categories.xlsx") -> dict[str, Category]:
    df = pd.read_excel(path)
    out: dict[str, Category] = {}
    for _, r in df.iterrows():
        name = str(r.get("分类名称", "")).strip()
        if not name or name == "nan":
            continue
        out[name] = Category(
            name=name,
            level=str(r.get("分类级别", "")).strip(),
            path=str(r.get("向量匹配分类描述", "")).split("层级路径：")[-1].split("。")[0].strip(),
            description=str(r.get("向量匹配分类描述", "")),
        )
    return out
```

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/test_categories.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add addr/types.py addr/categories.py tests/test_categories.py
git commit -m "feat: category catalog loader with level awareness"
```

---

## Task 3: 文本规范化与模式识别

**Files:**
- Create: `addr/normalize.py`, `tests/test_normalize.py`

- [ ] **Step 1: 写失败测试**

```python
from addr.normalize import normalize, detect_mode, split_fields

def test_normalize_collapses_and_strips():
    assert normalize("  长沙　市 ") == "长沙 市"

def test_detect_mode():
    assert detect_mode("某某诊所", "长沙市天心区X路1号") == "has_name"
    assert detect_mode("", "长沙市天心区X路1号") == "address_only"

def test_split_fields_pure_address_in_name_col():
    name, addr = split_fields("湖南省长沙市天心区X路1号", "")
    assert name == "" and addr == "湖南省长沙市天心区X路1号"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_normalize.py -q`
Expected: FAIL

- [ ] **Step 3: 写 addr/normalize.py**

```python
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
    if len(name) >= 18 and _ADDRESS_SIGNAL.search(name):
        return "address_only"
    return "has_name" if name else "address_only"

def split_fields(name: str, address: str) -> tuple[str, str]:
    name, address = normalize(name), normalize(address)
    if not address and detect_mode(name, address) == "address_only":
        return "", name
    return name, address
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_normalize.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add addr/normalize.py tests/test_normalize.py
git commit -m "feat: text normalization and input-mode detection"
```

---

## Task 4: 主体定位(剥离行政前缀与登记/分店后缀)

**Files:**
- Create: `addr/segment.py`, `tests/test_segment.py`

- [ ] **Step 1: 写失败测试**

```python
from addr.segment import main_entity

def test_strip_admin_prefix():
    assert main_entity("长沙市天心区某某诊所") == "某某诊所"

def test_strip_registration_paren():
    # 登记主体括号被剥离,保留功能实体
    assert main_entity("长沙南海医院（湖南南海医院管理有限公司）") == "南海医院"

def test_strip_branch_suffix():
    assert main_entity("陈氏面瘫(长沙店)") == "陈氏面瘫"

def test_keep_when_no_prefix():
    assert main_entity("同仁堂国医馆") == "同仁堂国医馆"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_segment.py -q`
Expected: FAIL

- [ ] **Step 3: 写 addr/segment.py**

```python
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
# 末尾括号内的登记/分店信息:（…有限公司）(…店) (NO.xxx) 等
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
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_segment.py -q`
Expected: PASS（若 `南海医院` 用例因前缀贪婪失败,缩小 `_ADMIN_PREFIX` 的市级匹配为非贪婪并重试）

- [ ] **Step 5: Commit**

```bash
git add addr/segment.py tests/test_segment.py
git commit -m "feat: main-entity segmentation (strip admin prefix + reg/branch suffix)"
```

---

## Task 5: 从描述列自动生成通名词典

**Files:**
- Create: `addr/build_dict.py`, `tests/test_build_dict.py`
- Generate: `dict/tongming.auto.yaml`

- [ ] **Step 1: 写失败测试**

```python
from addr.build_dict import build_tongming_auto
from addr.categories import load_catalog

def test_build_extracts_terms_from_shiyongduixiang(tmp_path):
    cat = load_catalog("categories.xlsx")
    out = tmp_path / "tongming.auto.yaml"
    index = build_tongming_auto(cat, str(out))
    # "酒楼" 出现在餐馆类"适用对象",应映射到含餐的分类
    assert any("餐" in c for c in index.get("酒楼", []))
    assert out.exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_build_dict.py -q`
Expected: FAIL

- [ ] **Step 3: 写 addr/build_dict.py**

```python
from __future__ import annotations
import re
import yaml
from addr.types import Category

_APPLY = re.compile(r"适用对象：(.+?)(。|$)")
_SPLIT = re.compile(r"[、，,/；;]")

def build_tongming_auto(catalog: dict[str, Category], out_path: str) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    def add(term: str, name: str):
        term = term.strip()
        if len(term) < 2:
            return
        index.setdefault(term, [])
        if name not in index[term]:
            index[term].append(name)
    for name, c in catalog.items():
        add(name, name)                       # 分类名本身
        m = _APPLY.search(c.description)
        if m:
            for term in _SPLIT.split(m.group(1)):
                term = re.sub(r"[等\s]+$", "", term)
                if term:
                    add(term, name)
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(index, f, allow_unicode=True, sort_keys=True)
    return index
```

- [ ] **Step 4: 运行确认通过,并生成正式词典**

Run: `pytest tests/test_build_dict.py -q`
Expected: PASS
Run: `python -c "from addr.build_dict import build_tongming_auto as b; from addr.categories import load_catalog as l; b(l('categories.xlsx'),'dict/tongming.auto.yaml')"`
Expected: 生成 `dict/tongming.auto.yaml`

- [ ] **Step 5: Commit**

```bash
git add addr/build_dict.py tests/test_build_dict.py dict/tongming.auto.yaml
git commit -m "feat: auto-build 通名 dictionary from category descriptions"
```

---

## Task 6: 词典加载与 Context 装配

**Files:**
- Create: `addr/dictionaries.py`, `tests/test_dictionaries.py`
- Create 空种子: `dict/tongming.override.yaml`, `dict/modifiers.yaml`, `dict/levels.yaml`, `dict/gazetteer.yaml`, `dict/denylist.yaml`

- [ ] **Step 1: 建 5 个种子词典文件(先放最小内容,Task 10 充实)**

```yaml
# dict/tongming.override.yaml  —— term -> [分类名...];override 覆盖 auto
学校: []          # 裸"学校"不映射(陷阱类"学校报名处"需明确"报名"才命中)
```
```yaml
# dict/modifiers.yaml  —— 多义通名消歧
[]
```
```yaml
# dict/levels.yaml  —— 行政级别前缀
[]
```
```yaml
# dict/gazetteer.yaml  —— 品牌 -> 分类名
{}
```
```yaml
# dict/denylist.yaml  —— 排斥规则
[]
```

- [ ] **Step 2: 写失败测试**

```python
from addr.dictionaries import load_context

def test_context_merges_auto_and_override():
    ctx = load_context(dict_dir="dict", catalog_path="categories.xlsx")
    # override 把"学校"置空,覆盖 auto
    assert ctx.tongming.get("学校", []) == []
    # auto 里仍有通名
    assert "综合医院" in ctx.catalog
```

- [ ] **Step 3: 运行确认失败**

Run: `pytest tests/test_dictionaries.py -q`
Expected: FAIL

- [ ] **Step 4: 写 addr/dictionaries.py**

```python
from __future__ import annotations
import os
import yaml
from addr.types import Context
from addr.categories import load_catalog

def _load_yaml(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or default

def load_context(dict_dir: str = "dict", catalog_path: str = "categories.xlsx") -> Context:
    auto = _load_yaml(f"{dict_dir}/tongming.auto.yaml", {})
    override = _load_yaml(f"{dict_dir}/tongming.override.yaml", {})
    tongming = dict(auto)
    tongming.update(override)                      # override 覆盖(含置空)
    return Context(
        catalog=load_catalog(catalog_path),
        tongming=tongming,
        modifiers=_load_yaml(f"{dict_dir}/modifiers.yaml", []),
        levels=_load_yaml(f"{dict_dir}/levels.yaml", []),
        gazetteer=_load_yaml(f"{dict_dir}/gazetteer.yaml", {}),
        denylist=_load_yaml(f"{dict_dir}/denylist.yaml", []),
    )
```

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/test_dictionaries.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add addr/dictionaries.py tests/test_dictionaries.py dict/*.yaml
git commit -m "feat: dictionary loader and Context assembly (override beats auto)"
```

---

## Task 7: 通名抽取与候选生成

**Files:**
- Create: `addr/tongming.py`, `tests/test_tongming.py`

- [ ] **Step 1: 写失败测试**

```python
from addr.tongming import extract_primary, candidates
from addr.dictionaries import load_context

CTX = load_context()

def test_primary_is_rightmost_longest():
    # "国医馆"应作为主通名被抽出(最右最长)
    term = extract_primary("同仁堂国医馆", CTX.tongming)
    assert term in ("国医馆", "医馆")

def test_candidates_nonempty_for_known_tongming():
    cands = candidates("某某综合医院", CTX)
    assert any(c.category == "综合医院" for c in cands)
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_tongming.py -q`
Expected: FAIL

- [ ] **Step 3: 写 addr/tongming.py**

```python
from __future__ import annotations
from addr.types import Candidate, Context

def _matches(text: str, terms) -> list[tuple[int, int, str]]:
    """返回 (起点, 长度, 词) 列表,词在 text 中出现的。"""
    hits = []
    for term in terms:
        if not term:
            continue
        idx = text.rfind(term)
        if idx >= 0:
            hits.append((idx, len(term), term))
    return hits

def extract_primary(text: str, tongming: dict) -> str | None:
    hits = _matches(text, tongming.keys())
    if not hits:
        return None
    # 主通名:最右(起点+长度最大),并列取最长
    hits.sort(key=lambda h: (h[0] + h[1], h[1]))
    return hits[-1][2]

def candidates(text: str, ctx: Context) -> list[Candidate]:
    out: list[Candidate] = []
    seen = set()
    hits = _matches(text, ctx.tongming.keys())
    hits.sort(key=lambda h: (h[0] + h[1], h[1]), reverse=True)  # 偏好靠右的词
    for _, _, term in hits:
        for cat in ctx.tongming.get(term, []):
            if cat and cat not in seen:
                seen.add(cat)
                out.append(Candidate(category=cat, source="通名", evidence=term))
    return out
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_tongming.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add addr/tongming.py tests/test_tongming.py
git commit -m "feat: 通名 extraction (rightmost/longest) and candidate generation"
```

---

## Task 8: 修饰词消歧与行政级别判定

**Files:**
- Create: `addr/disambiguate.py`, `tests/test_disambiguate.py`

- [ ] **Step 1: 写失败测试**

```python
from addr.disambiguate import disambiguate, gov_level
from addr.types import Candidate

MODIFIERS = [
    {"tongming": "中心", "if_any": ["考试", "测试中心"], "then": "考试中心"},
    {"tongming": "中心", "if_any": ["应急", "管理", "指挥", "防御", "监测"], "then": "政府及管理机构"},
    {"tongming": "医院", "if_any": ["宠物", "动物"], "then": "宠物医院"},
    {"tongming": "医院", "if_any": ["口腔", "眼", "皮肤", "骨", "专科"], "then": "专科医院"},
]
LEVELS = [
    {"prefix_any": ["国家", "全国", "中华人民共和国"], "level": "国家级政府机关"},
    {"prefix_any": ["省", "自治区", "湖南省"], "level": "省级政府机关"},
    {"prefix_any": ["市", "长沙市"], "level": "地级市级政府机关"},
    {"prefix_any": ["区", "县"], "level": "区县级政府机关"},
]

def test_disambiguate_picks_by_modifier():
    cands = [Candidate("考试中心", "通名", "中心"), Candidate("政府及管理机构", "通名", "中心")]
    cat, why = disambiguate(cands, "湖南省气象灾害防御技术中心", "中心", MODIFIERS)
    assert cat == "政府及管理机构"
    assert "防御" in why

def test_gov_level_from_prefix():
    assert gov_level("湖南省水利厅", LEVELS) == "省级政府机关"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_disambiguate.py -q`
Expected: FAIL

- [ ] **Step 3: 写 addr/disambiguate.py**

```python
from __future__ import annotations
from addr.types import Candidate

def disambiguate(cands: list[Candidate], full_text: str, primary_tongming: str,
                 modifiers: list) -> tuple[str | None, str]:
    if not cands:
        return None, "无候选"
    if len(cands) == 1:
        return cands[0].category, "唯一候选"
    cat_set = {c.category for c in cands}
    for rule in modifiers:
        if rule.get("tongming") != primary_tongming:
            continue
        if rule.get("then") not in cat_set:
            continue
        hit = next((w for w in rule.get("if_any", []) if w in full_text), None)
        if hit:
            return rule["then"], f"修饰词'{hit}'→{rule['then']}"
    # 无消歧命中:返回首候选但标注不确定
    return cands[0].category, "多候选未消歧,取首候选"

def gov_level(full_text: str, levels: list) -> str:
    for rule in levels:
        if any(full_text.startswith(p) or p in full_text[:6] for p in rule.get("prefix_any", [])):
            return rule["level"]
    return ""
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_disambiguate.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add addr/disambiguate.py tests/test_disambiguate.py
git commit -m "feat: modifier disambiguation and government admin-level detection"
```

---

## Task 9: 品牌兜底

**Files:**
- Create: `addr/gazetteer.py`, `tests/test_gazetteer.py`

- [ ] **Step 1: 写失败测试**

```python
from addr.gazetteer import brand_hit

GAZ = {"仟吉": "面包房", "富侨": "洗浴中心、SPA、足浴"}

def test_brand_hit():
    c = brand_hit("仟吉西饼解放路店", GAZ)
    assert c is not None and c.category == "面包房"

def test_brand_miss():
    assert brand_hit("某某不知名小店", GAZ) is None
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_gazetteer.py -q`
Expected: FAIL

- [ ] **Step 3: 写 addr/gazetteer.py**

```python
from __future__ import annotations
from addr.types import Candidate

def brand_hit(name: str, gazetteer: dict) -> Candidate | None:
    for brand, category in gazetteer.items():
        if brand and brand in name:
            return Candidate(category=category, source="品牌", evidence=brand)
    return None
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_gazetteer.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add addr/gazetteer.py tests/test_gazetteer.py
git commit -m "feat: brand gazetteer fallback"
```

---

## Task 10: 裁决与置信分层

**Files:**
- Create: `addr/arbitrate.py`, `tests/test_arbitrate.py`

- [ ] **Step 1: 写失败测试**

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_arbitrate.py -q`
Expected: FAIL

- [ ] **Step 3: 写 addr/arbitrate.py**

```python
from __future__ import annotations
from addr.types import Candidate, Result

def _denied(category: str, name: str, address: str, full_text: str, denylist: list) -> bool:
    for rule in denylist:
        if rule.get("target") != category:
            continue
        if rule.get("positive_any") and not any(w in full_text for w in rule["positive_any"]):
            continue
        if rule.get("name_negative_any") and any(w in name for w in rule["name_negative_any"]):
            continue  # 名称里有银行等→是本体,不排斥
        if rule.get("address_any") and not any(w in address for w in rule["address_any"]):
            continue
        return True
    return False

def arbitrate(cands: list[Candidate], name: str, full_text: str,
              disambig_reason: str, denylist: list, address: str = "") -> Result:
    kept = [c for c in cands if not _denied(c.category, name, address or full_text, full_text, denylist)]
    if not kept:
        return Result(category="待复核", level="", confidence="review",
                      matched_tongming="", candidates="", disambig=disambig_reason,
                      gov_level="", review=True, reason="无可用候选")
    best = kept[0]
    conf = "gold" if (len(kept) == 1 or "修饰词" in disambig_reason or best.source == "品牌") else "silver"
    return Result(category=best.category, level="", confidence=conf,
                  matched_tongming=best.evidence, candidates=" | ".join(c.category for c in kept),
                  disambig=disambig_reason, gov_level="", review=(conf != "gold"),
                  reason=f"{best.source}:{best.evidence}")
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_arbitrate.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add addr/arbitrate.py tests/test_arbitrate.py
git commit -m "feat: arbitration with denylist and confidence tiering"
```

---

## Task 11: 主管线编排 + 种子词典 + 已知错例验收

**Files:**
- Create: `addr/classify.py`, `tests/test_classify_integration.py`
- Modify: `dict/tongming.override.yaml`, `dict/modifiers.yaml`, `dict/levels.yaml`, `dict/gazetteer.yaml`, `dict/denylist.yaml`(充实种子)

- [ ] **Step 1: 充实种子词典(覆盖已知失败族)**

`dict/tongming.override.yaml` 增补(节选,实现时按需补全同族):
```yaml
学校: []
中等职业学校: [中专/职高/技校]
职业技术学校: [中专/职高/技校]
外国语学校: [中学]
振兴局: [政府及管理机构]
管理局: [政府及管理机构]
应急管理厅: [政府及管理机构]
水利厅: [省级政府机关]
商务厅: [省级政府机关]
人民代表大会: [省级政府机关]
常务委员会: [省级政府机关]
国医馆: [私人诊所]
中医馆: [私人诊所]
名医馆: [私人诊所]
郎中: [私人诊所]
鼻炎馆: [私人诊所]
面瘫: [私人诊所]
皮肤病专科: [专科医院]
```
`dict/modifiers.yaml` 增补(节选):
```yaml
- {tongming: 中心, if_any: [考试, 测试], then: 考试中心}
- {tongming: 中心, if_any: [应急, 管理, 指挥, 防御, 监测, 信息, 政务, 服务], then: 政府及管理机构}
- {tongming: 院, if_any: [机关, 二院, 政府], then: 省级政府机关}
- {tongming: 医院, if_any: [宠物, 动物], then: 宠物医院}
- {tongming: 医院, if_any: [口腔, 眼, 皮肤, 骨, 专科], then: 专科医院}
```
`dict/levels.yaml`:
```yaml
- {prefix_any: [国家, 全国, 中华人民共和国], level: 国家级政府机关}
- {prefix_any: [湖南省, 省, 自治区], level: 省级政府机关}
- {prefix_any: [长沙市, 市], level: 地级市级政府机关}
- {prefix_any: [区, 县], level: 区县级政府机关}
```
`dict/gazetteer.yaml`:
```yaml
仟吉: 面包房
富侨: 洗浴中心、SPA、足浴
```
`dict/denylist.yaml`:
```yaml
- {target: 金融服务, positive_any: [银行], address_any: [对面, 旁边, 附近, 正北方向, 正南方向], name_negative_any: [银行, 支行, 分行, ATM]}
```

- [ ] **Step 2: 写集成测试(已知错例当验收)**

```python
import pytest
from addr.classify import classify_one
from addr.dictionaries import load_context

CTX = load_context()

CASES = [
    ("湖南建设中等职业学校", "中专/职高/技校"),
    ("长沙市雅礼外国语学校", "中学"),
    ("同仁堂国医馆", "私人诊所"),
    ("湖南长沙正尔皮肤病专科", "专科医院"),
    ("长沙南海医院（湖南南海医院管理有限公司）", "综合医院"),
    ("湖南省气象灾害防御技术中心", "政府及管理机构"),
    ("湖南省水利厅", "省级政府机关"),
]

@pytest.mark.parametrize("name,expected", CASES)
def test_known_failures_now_fixed(name, expected):
    res = classify_one(name, "", CTX)
    assert res.category == expected, f"{name} -> {res.category} (期望 {expected}), 理由={res.reason}"
```

- [ ] **Step 3: 运行确认失败**

Run: `pytest tests/test_classify_integration.py -q`
Expected: FAIL（`addr.classify` 不存在）

- [ ] **Step 4: 写 addr/classify.py**

```python
from __future__ import annotations
import pandas as pd
from addr.types import Context, Result
from addr.normalize import split_fields
from addr.segment import main_entity
from addr.tongming import extract_primary, candidates
from addr.disambiguate import disambiguate, gov_level
from addr.gazetteer import brand_hit
from addr.arbitrate import arbitrate

_GOV = {"政府及管理机构", "省级政府机关", "国家级政府机关",
        "地级市级政府机关", "区县级政府机关"}

def classify_one(name: str, address: str, ctx: Context) -> Result:
    name, address = split_fields(name, address)
    full = " ".join(p for p in [name, address] if p)
    entity = main_entity(name) if name else address
    cands = candidates(entity, ctx)
    primary = extract_primary(entity, ctx.tongming) or ""
    if cands:
        cat, why = disambiguate(cands, full, primary, ctx.modifiers)
        cands = [c for c in cands if c.category == cat] + [c for c in cands if c.category != cat]
    else:
        why = "无通名"
        brand = brand_hit(name, ctx.gazetteer)
        if brand:
            cands = [brand]
            why = f"品牌:{brand.evidence}"
    res = arbitrate(cands, name, full, why, ctx.denylist, address)
    # 政府机关:用前缀细化行政级别
    if res.category in _GOV:
        lvl = gov_level(full, ctx.levels)
        if lvl:
            res.gov_level = lvl
            if res.category == "政府及管理机构" and lvl in ctx.catalog:
                pass  # 保留二级"政府及管理机构"或按需细化,详见 spec 层级感知原则
    res.level = ctx.catalog[res.category].level if res.category in ctx.catalog else ""
    return res

def classify_df(df: pd.DataFrame, ctx: Context, name_col: str, address_col: str | None) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        nm = str(r.get(name_col, "")) if name_col else ""
        ad = str(r.get(address_col, "")) if address_col else ""
        res = classify_one(nm, ad, ctx)
        out = r.to_dict()
        out.update({
            "原始名称": nm, "原始地址": ad, "最终标准分类": res.category,
            "分类级别": res.level, "命中通名": res.matched_tongming,
            "候选": res.candidates, "消歧依据": res.disambig,
            "行政级别": res.gov_level, "置信": res.confidence,
            "需复核": "是" if res.review else "否", "理由": res.reason,
        })
        rows.append(out)
    return pd.DataFrame(rows)
```

- [ ] **Step 5: 运行确认通过(若个别用例不过,调对应 override/modifier 条目,不改引擎)**

Run: `pytest tests/test_classify_integration.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add addr/classify.py tests/test_classify_integration.py dict/*.yaml
git commit -m "feat: pipeline orchestration + seed dicts; known failures now pass"
```

---

## Task 12: 命令行入口与 Excel 读写

**Files:**
- Create: `addr/cli.py`, `tests/test_cli.py`

- [ ] **Step 1: 写失败测试**

```python
import pandas as pd
from addr.cli import run

def test_run_writes_output(tmp_path):
    inp = tmp_path / "in.xlsx"
    out = tmp_path / "out.xlsx"
    pd.DataFrame({"名称": ["同仁堂国医馆"], "地址": [""]}).to_excel(inp, index=False)
    run(str(inp), str(out))
    df = pd.read_excel(out)
    assert "最终标准分类" in df.columns
    assert df.loc[0, "最终标准分类"] == "私人诊所"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_cli.py -q`
Expected: FAIL

- [ ] **Step 3: 写 addr/cli.py**

```python
from __future__ import annotations
import argparse
import pandas as pd
from addr.dictionaries import load_context
from addr.classify import classify_df
from addr.normalize import normalize

def _pick(df, names):
    cols = {str(c).strip(): c for c in df.columns}
    for n in names:
        if n in cols:
            return cols[n]
    return None

def run(input_path: str, output_path: str, limit: int = 0) -> None:
    ctx = load_context()
    df = pd.read_excel(input_path)
    if limit:
        df = df.head(limit).copy()
    name_col = _pick(df, ["名称", "POI名称", "名字", "name"])
    addr_col = _pick(df, ["地址", "详细地址", "位置", "address"])
    if name_col is None and addr_col is None:
        name_col = df.columns[0]
    result = classify_df(df, ctx, name_col, addr_col)
    result.to_excel(output_path, index=False)
    n_review = (result["需复核"] == "是").sum()
    print(f"完成:{output_path} 共{len(result)}行,需复核{n_review}行")

def main():
    p = argparse.ArgumentParser(description="通名驱动地址分类器")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()
    run(a.input, a.output, a.limit)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_cli.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add addr/cli.py tests/test_cli.py
git commit -m "feat: CLI with Excel I/O and explanation columns"
```

---

## Task 13: 评测/回归工作流

**Files:**
- Create: `eval/run_eval.py`, `eval/regression.jsonl`(空文件), `tests/test_eval.py`

- [ ] **Step 1: 建空回归集**

`eval/regression.jsonl` 创建为空文件。

- [ ] **Step 2: 写失败测试**

```python
import json
from eval.run_eval import evaluate

def test_evaluate_on_small_set(tmp_path):
    reg = tmp_path / "reg.jsonl"
    reg.write_text(
        json.dumps({"name": "同仁堂国医馆", "address": "", "label": "私人诊所"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    acc, total, wrong = evaluate(str(reg))
    assert total == 1
    assert acc == 1.0
    assert wrong == []
```

- [ ] **Step 3: 运行确认失败**

Run: `pytest tests/test_eval.py -q`
Expected: FAIL

- [ ] **Step 4: 写 eval/run_eval.py(含 eval/__init__.py)**

创建 `eval/__init__.py`(单行 `# package`)与:
```python
from __future__ import annotations
import json
from addr.dictionaries import load_context
from addr.classify import classify_one

def evaluate(regression_path: str) -> tuple[float, int, list]:
    ctx = load_context()
    total, correct, wrong = 0, 0, []
    with open(regression_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            total += 1
            res = classify_one(row["name"], row.get("address", ""), ctx)
            if res.category == row["label"]:
                correct += 1
            else:
                wrong.append({"name": row["name"], "got": res.category,
                              "want": row["label"], "reason": res.reason})
    acc = correct / total if total else 0.0
    return acc, total, wrong

if __name__ == "__main__":
    import sys
    acc, total, wrong = evaluate(sys.argv[1] if len(sys.argv) > 1 else "eval/regression.jsonl")
    print(f"准确率 {acc:.1%} ({total} 条)")
    for w in wrong:
        print(f"  ✗ {w['name']}: 判={w['got']} 期望={w['want']} ({w['reason']})")
```

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/test_eval.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add eval/__init__.py eval/run_eval.py eval/regression.jsonl tests/test_eval.py
git commit -m "feat: regression eval harness (grows from spot-checks)"
```

---

## Task 14: 全量回归 + 旧代码清理 + README

**Files:**
- Delete: `text_rules.py`, `retrieval.py`, `deep_model.py`, `classify.py`(根目录旧版)
- Modify: `README.md`

- [ ] **Step 1: 全量跑一遍真实数据,人工抽查 review 队列**

Run: `python -m addr.cli --input data/input/地址_625.xlsx --output data/output/重做_625.xlsx`
Expected: 打印总行数与需复核行数;打开输出抽查 `需复核=是` 的行,把纠正的样本按 `{"name","address","label"}` 追加进 `eval/regression.jsonl`。

- [ ] **Step 2: 跑评测**

Run: `python -m eval.run_eval eval/regression.jsonl`
Expected: 打印准确率与错例清单(此时回归集为人工抽查所得)。

- [ ] **Step 3: 删除旧实现**

```bash
git rm classify.py text_rules.py retrieval.py deep_model.py
```

- [ ] **Step 4: 确认测试全绿(无对旧模块的残留依赖)**

Run: `pytest -q`
Expected: 全部 PASS

- [ ] **Step 5: 更新 README.md**

README 用一段说明新架构:`python -m addr.cli --input ... --output ...`;词典在 `dict/`;评测在 `eval/`;迭代方式=抽查 review→补 `dict/*.override/modifiers/gazetteer`→重跑 `eval`。删除旧版 embedding/深度兜底相关章节。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: remove legacy pipeline, update README for 通名 engine"
```

---

## Self-Review(已执行)

- **Spec 覆盖**:① normalize(T3)② segment(T4)③④ tongming(T5,T7)⑤⑥ disambiguate(T8)⑦⑨ arbitrate(T10)⑧ gazetteer(T9)分类体系/描述列自动生成(T5)层级感知(T2 level + T11)无真值集工作流(T13,T14)测试(各 Task TDD + T13 回归)。开放点(导出兼容)按 spec 暂不实现。✓
- **占位符扫描**:无 TBD/TODO;种子词典为"真实条目+同族补全说明",属数据内容而非代码占位。✓
- **类型一致性**:`Candidate(category, source, evidence)`、`Result(...)`、`Context(...)`、`classify_one(name,address,ctx)`、`load_context()` 全程签名一致。✓
- 已知风险:`segment.main_entity` 的行政前缀正则可能过贪婪(T4 Step4 已给回退指引);政府二级"政府及管理机构"是否细化到 `gov_level` 由实现期按 spec 层级感知取舍(T11 已留注释)。
