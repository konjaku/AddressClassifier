# 地址/POI 名称标准分类器(通名驱动版)

把 POI 的「名称/地址」批量映射到 `categories.xlsx` 的标准分类(16 一级 / 52 二级 / 326 三级)。

本版是对旧 Codex 版的**重做**:纯传统算法、完全离线、零模型(不用 LLM/embedding)、完全可解释。核心思路是**通名(中心词)驱动的确定性分类**,而不是字符模糊相似度。设计与实现计划见 `docs/superpowers/`。

## 1. 运行

```bash
python3 -m addr.cli --input data/input/地址_5000.xlsx --output data/output/结果.xlsx
# 只跑前 N 行:加 --limit 100
```

依赖只有 `pandas / openpyxl / PyYAML`(见 `requirements.txt`),无任何模型。

## 2. 思路:九步管线

```
① 规范化与切分   ② 主体定位(剥行政前缀+登记/分店后缀)
③ 通名抽取(最右/最长) ④ 通名→候选类(词典)
⑤ 修饰词消歧     ⑥ 行政级别判定(政府类)
⑦ 优先级裁决+排斥 ⑧ 品牌兜底  ⑨ 置信分层
```

四条原则:**层级感知**(拿不准就出较高层级,不硬凑三级)、**零模糊相似度**(判不出显式标「待复核」,绝不塞「其他服务」)、**全程可解释**、**陷阱通名硬约束**(裸「学校」「中心」等必须过消歧)。

## 3. 代码结构(`addr/`)

| 模块 | 职责 |
|---|---|
| `normalize.py` | 文本规范化、名称/地址切分、纯地址识别 |
| `segment.py` | 剥离行政前缀 + 登记/分店后缀,定位主体 |
| `tongming.py` | 通名抽取(最右/最长)+ 层级感知候选排序 |
| `disambiguate.py` | 修饰词消歧(权威覆盖)+ 行政级别 |
| `gazetteer.py` | 品牌强实体兜底 |
| `arbitrate.py` | 优先级裁决 + 排斥规则 + 置信分层 |
| `classify.py` | 管线编排 + DataFrame 处理 |
| `cli.py` | Excel 读写命令行 |
| `build_dict.py` | 离线工具:从 `categories.xlsx` 描述列生成基础词典 |

## 4. 词典(`dict/`,改这里不改代码)

```
tongming.auto.yaml      由 build_dict 从"适用对象"自动生成(勿手改)
tongming.override.yaml  人工:陷阱通名(学校/中心置空)、补漏、纠偏;override 覆盖 auto
modifiers.yaml          多义通名消歧(中心:应急/防御→政府;医院:宠物→宠物医院)
levels.yaml             行政级别前缀(国家/省/市/区)
gazetteer.yaml          品牌强实体(仟吉→面包房)
denylist.yaml           排斥/降权(地址里"银行对面"不算银行)
```

`categories.xlsx` 变更后重新生成基础词典:

```bash
python3 -c "from addr.build_dict import build_tongming_auto as b; from addr.categories import load_catalog as l; b(l('categories.xlsx'),'dict/tongming.auto.yaml')"
```

## 5. 输出与置信

输出在原列基础上追加:`最终标准分类 / 分类级别 / 命中通名 / 候选 / 消歧依据 / 行政级别 / 置信 / 需复核 / 理由`。

置信分层:`gold`(清晰可直接用)/ `silver`(消歧不定,建议复核)/ `review`(无通名或判不出 → 分类记为「待复核」)。`需复核=是` 的行进人工复核队列。

## 6. 迭代方式(无固定真值集)

```
跑一版 → 抽查"需复核"队列 → 把纠正结果按 {"name","address","label"}
追加进 eval/regression.jsonl → 重跑评测,保证已对的不回退
```

```bash
python3 -m eval.run_eval eval/regression.jsonl
```

要扩覆盖、纠错,优先改 `dict/*.yaml`(override / modifiers / gazetteer / denylist),而不是改代码。

## 7. 测试

```bash
pytest -q
```
