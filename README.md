# 地址名称标准分类器

本目录是整理后的交付版项目。文件名和输出列名已经去掉实验版本号，代码压缩为 4 个 Python 文件，文档压缩为当前这一个 `README.md`。

## 1. 文件结构

```text
AddressClassifier/
  classify.py          主入口：读取 Excel、调度规则/检索/深度兜底、导出结果
  text_rules.py        文本清洗、名称锚定、强规则、外置词典、排斥规则
  retrieval.py         标准分类加载、字符检索、多路仲裁
  deep_model.py        Qwen embedding 核心类型兜底、MPS/CPU 运行

  categories.xlsx      标准分类表
  rules.yaml           外置 POI 词典
  core_types.yaml      深度兜底核心类型原型

  models/
    embedding          Qwen embedding 模型目录软链接

  data/
    input/             输入数据
    output/            输出结果
```

代码文件只有：

```text
classify.py
text_rules.py
retrieval.py
deep_model.py
```

## 2. 总体思路

系统不是把所有地址直接丢给大模型，而是分层处理：

```text
输入 Excel
  -> 名称/地址识别
  -> 文本清洗
  -> 名称强实体锚定
  -> 外置词典规则
  -> 强规则候选
  -> 字符检索候选
  -> 多路仲裁
  -> 低置信样本进入 embedding 深度兜底
  -> 导出 Excel
```

核心原则：

```text
1. 名称中的功能实体优先于地址里的楼栋、门牌、附近地标。
2. 标准分类名只来自 categories.xlsx，不自造分类。
3. 规则、外置词典和字符检索负责快速覆盖大部分数据。
4. embedding 只处理低置信样本。
5. 深度兜底只有强采纳才覆盖原结果。
```

## 3. 输入格式

推荐 Excel 列：

```text
名称
地址
```

纯地址数据推荐：

```text
名称列留空
地址列放地址
```

如果只有一列地址，也可以放到第一列；系统会根据“省、市、区、街道、路、号、栋、单元”等地址结构尝试识别为纯地址。

## 4. 快速运行

进入目录：

```bash
cd /Users/mac/Code/Work/AddressClassifier
```

快速规则版，不启用 embedding：

```bash
python3 -u classify.py \
  --input data/input/地址_5000.xlsx \
  --output data/output/分类结果.xlsx
```

只跑前 100 条：

```bash
python3 -u classify.py \
  --input data/input/地址_5000.xlsx \
  --output data/output/抽样结果.xlsx \
  --limit 100
```

## 5. 正式深度版

CPU 深度兜底：

```bash
python3 -u classify.py \
  --input data/input/地址_5000.xlsx \
  --output data/output/分类结果_深度.xlsx \
  --enable-deep \
  --deep-device cpu \
  --deep-batch-size 8
```

Apple 芯片 MPS 深度兜底：

```bash
PYTORCH_ENABLE_MPS_FALLBACK=1 TOKENIZERS_PARALLELISM=false python3 -u classify.py \
  --input data/input/地址_5000.xlsx \
  --output data/output/分类结果_MPS.xlsx \
  --enable-deep \
  --deep-device mps \
  --deep-batch-size 1
```

MPS 注意事项：

```text
1. Codex 默认沙箱内可能无法访问 Metal/MPS。
2. 普通 VSCode 终端或沙箱外运行可用。
3. M2 Air 8GB 建议从 batch_size=1 开始。
4. 确认不卡顿后再尝试 batch_size=2 或 4。
```

先检查 MPS：

```bash
PYTORCH_ENABLE_MPS_FALLBACK=1 python3 - <<'PY'
import torch
print(torch.backends.mps.is_built())
print(torch.backends.mps.is_available())
PY
```

两个都为 `True` 才能用 `--deep-device mps`。

## 6. 规则层原理

`text_rules.py` 包含三类可解释规则。

名称锚定：

```text
口腔/牙科 -> 牙科诊所
眼科/眼视光/视光/视力/护眼/验光 -> 专科医院/体检机构/私人诊所
小学/中学/大学 -> 对应教育分类
居委会/村委会 -> 村委会/居委会
警务站/执勤点 -> 派出所
监管局/发改委 -> 政府机关
```

强规则：

```text
彩票 -> 彩票销售
银行/支行/分行 -> 金融服务
邮政/EMS -> 邮局/物流
酒店/宾馆 -> 住宿
药店/药房 -> 药店
眼科/视光/验光 -> 专科医院/体检机构/私人诊所
餐厅/饭店/粉店/面馆 -> 餐饮
```

外置词典 `rules.yaml` 分三层：

```text
hard_override     高精度强锚定，可覆盖
candidate_boost   候选加分，只参与仲裁
deny_or_demote    排斥/降权，防止误判
```

例子：

```text
地产/房产 + 分行 -> 排斥金融服务
银行对面/银行旁边 -> 排斥金融服务
公司北院/公司南园小区 + 栋 -> 排斥公司
```

## 7. 字符检索原理

`retrieval.py` 使用字符 ngram TF-IDF 检索标准分类描述。

作用：

```text
1. 当规则没有命中时，提供文本相似候选。
2. 适合中文短文本，不依赖分词。
3. 速度快，可大批量运行。
```

## 8. 深度兜底原理

`deep_model.py` 使用 Qwen embedding。

它不直接匹配全部标准分类，而是先匹配 `core_types.yaml` 中的核心类型：

```text
餐饮
零售
医疗健康
教育培训
金融网点
小区楼盘
纯地址定位链
政府事业单位
生活服务
```

流程：

```text
低置信样本
  -> 构造短 query
  -> Qwen 编码 query
  -> Qwen 编码核心类型原型
  -> 计算相似度
  -> 得到 Top1 / Top2 核心类型
  -> 根据 map_to 映射回标准分类
  -> 按采纳规则决定是否覆盖
```

强采纳条件：

```text
1. 原结果不是 gold。
2. 分数达到阈值。
3. Top1/Top2 分差足够，或 Top2 合理反超。
4. 命中 required_any 关键词。
5. 未命中 denied_any 反例词。
6. 不违反风险类别关键词要求。
```

输出：

```text
strong_accept -> 覆盖最终分类
weak_suggest  -> 只记录建议，不覆盖
reject        -> 保持原分类
```

## 9. 输出字段

核心输出列：

```text
原始名称
原始地址
输入模式
词典候选
词典排斥降权
名称锚定候选
强规则候选
检索候选
候选汇总
最终标准分类
最终分数
最终匹配方式
最终置信度
标签等级
结果状态
最终原因
是否进入深度兜底
深度兜底Top1核心类型
深度兜底Top1分数
深度兜底Top2核心类型
深度兜底Top2分数
深度兜底建议标准分类
深度兜底采纳等级
是否采纳深度兜底
```

标签等级：

```text
gold    高置信，可直接使用
silver  中高置信，建议抽检
review  低置信，仍有最终分类，但建议关注
```

## 10. 维护方式

优先改配置，不要先改代码。

扩规则：

```text
改 rules.yaml
```

扩深度语义：

```text
改 core_types.yaml
```

改标准分类描述：

```text
改 categories.xlsx 的描述列
```

不要修改标准分类名，最终分类名必须来自 `categories.xlsx`。

## 11. 回归测试

每次修改后建议跑：

```bash
python3 -u classify.py --input data/input/地址_625.xlsx --output data/output/回归_625.xlsx
python3 -u classify.py --input data/input/地址_4555.xlsx --output data/output/回归_4555.xlsx
python3 -u classify.py --input data/input/地址_5000.xlsx --output data/output/回归_5000.xlsx
python3 -u classify.py --input data/input/地址_6000.xlsx --output data/output/回归_6000.xlsx
```

重点检查：

```text
其他单位/其他服务是否过多
银行对面是否误判金融服务
地产分行是否误判银行
公司宿舍/公司北院楼栋是否误判公司
小区门牌是否被商户名称错误覆盖
眼科/视光机构是否误判为洗浴、足浴或普通生活服务
```

## 12. 产品化建议

建议提供两种模式：

快速模式：

```text
规则 + 外置词典 + 字符检索
```

正式模式：

```text
快速模式 + MPS embedding 深度兜底
```

这样既能满足百万级速度，又能对低置信样本做语义精修。
