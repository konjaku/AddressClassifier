# 交接文档 — 地址/POI 名称分类器(通名驱动版)

> 给**毫无本项目背景**的接手者(人或 AI)。读完这份就能继续。日期:2026-06-15。

---

## 0. 一句话

把中文 POI 的「名称(+地址)」批量分类到 `categories.xlsx` 的标准分类(16 一级 / 52 二级 / 326 三级)。当前实现是**纯传统、完全离线、零模型的"通名(中心词)驱动确定性规则引擎"**。代码在 `addr/`,词典在 `dict/`,命令 `python3 -m addr.cli --input X.xlsx --output Y.xlsx`。

## 1. 硬约束(不可违反)

1. **完全离线**:最终跑在无外网的内网服务器,**禁止调用任何外部 API**(Claude/OpenAI 等)。
2. **纯传统算法**:**不用大模型,也不用 embedding 模型**。这是用户明确要求(上一版用 embedding 效果不好且离线难)。
3. **目标正确率 ~90%**(用户说 90% 即够)。
4. **没有真值集**:只能抽样人工核对。所以系统必须**极度可解释**,并靠抽查纠错**反哺词典**。

## 2. 背景与部署(用户提供,代码里看不到)

- 原项目由 OpenAI Codex 写,准确率 ~80%,不够,故重做。
- 一个旧版本**已集成进内网服务器,暂时不能改那边代码/文件**;只能看它的导出与错误(其格式与本地不同)。
- 用户给的 `data/input/地址_4555.xlsx` 是**开发/词典语料,不会进生产**——所以**针对它做覆盖、把它当词典素材是允许的**(映射要写成通用业态词,不要写成 4555 专属串,以便泛化)。
- `data/input/地址_625.xlsx` 偏政府/医疗/居委会(规整);`地址_4555.xlsx` 偏住宅门牌+小商户(更难、更广)。

## 3. 设计原则(改代码/词典时必须维持)

1. **层级感知**:输出能确信的**最深一层**;拿不准三级就退二级(如银行网点→「金融服务」二级),**绝不**为凑三级而错判,**绝不**塞「其他服务」。
2. **零模糊相似度**:判不出就显式标 **「待复核」**(诚实),不要猜。旧版正是因为"字符相似度撞类名"才把"乡村振兴局→度假村"。
3. **可解释**:每行输出带 命中通名/候选/消歧依据/理由。
4. **功能实体优先于登记主体**:"XX银行…有限公司"→金融服务,不是公司(靠"弱通名"机制,见 §5)。
5. **陷阱通名硬约束**:裸「学校」「中心」「生活馆」等禁用确定性默认(在 `dict/tongming.override.yaml` 里置 `[]`)。

## 4. 管线(`addr/classify.py: classify_one`)

```
名称/地址
 → normalize.split_fields      规范化、名称vs地址、纯地址(>=18字含地址信号)识别
 → segment.main_entity         剥离行政前缀(湖南省/长沙市/区,需带"省/市/区"标记)+ 末尾括号(…店)(…有限公司)
 → tongming.candidates(entity) 子串匹配词典得候选;功能通名优先于弱通名,再偏右,同通名内同名/更深层级优先
   tongming.extract_primary    主通名=最右(非弱)通名,末端同则最长
 → disambiguate.match_modifier 修饰词权威覆盖(即使候选空/不在候选里也成立):X中心+"防御/应急"→政府及管理机构
   disambiguate.disambiguate   多候选无修饰词命中时取首候选
 → (无候选时) gazetteer.brand_hit → menpai.menpai_category(entity) 住宅门牌兜底 → 否则 待复核
 → disambiguate.gov_level      政府类按前缀定行政级别(区县>市>省>国家,取最深),写入"行政级别"列(不改主分类)
 → arbitrate.arbitrate         denylist排斥 + 置信分层 gold/silver/review
```

## 5. 关键机制与"坑"(务必理解)

- **`python` 不存在,用 `python3`**。
- **词典两层**:`dict/tongming.auto.yaml`(由 `addr/build_dict.py` 从每个分类的"适用对象"描述**自动生成**,1365+ 条,**勿手改**)+ `dict/tongming.override.yaml`(**人工**,override **覆盖** auto,空列表 `[]` = 禁用该词)。改覆盖请改 override。
- **弱通名**(`addr/tongming.py: _WEAK`):公司/有限公司/集团/厂/工厂/商行/经营部/批发/总汇…。它们只在**没有其它功能通名**时才作主通名。所以"五金交电商行"→五金(非商行)。新增"登记/泛化后缀"应加进 `_WEAK`。
- **修饰词是权威的**(`match_modifier`):命中即采纳,不受候选集限制;且候选为空也能触发(用于裸"中心":`[]` + 修饰词救出政府类)。配置在 `dict/modifiers.yaml`。
- **门牌兜底**(`addr/menpai.py`)**只在无任何业态通名时**调用,且**必须传 `entity`(去过括号后缀的主体)**,否则会把分店地址"…(翡翠华庭店)"里的"华庭"误判成小区。有栋/单元/号→小区门牌;小区名或出入口(东南西北门)→小区。
- **行政级别**:`dict/levels.yaml` 按"最具体在前"排,`gov_level` 取首个命中=最深一级。它只填"行政级别"列做标注,**不改**主分类(主分类仍是政府及管理机构等)。
- **categories.xlsx 有跨级重名**(如"金融服务"既二级又三级、"餐馆"亦然);`load_catalog` 保留**首条**(较高层级)。
- **门牌/汽车等 auto 噪声**:auto 词典从描述生成,会有怪映射(曾出现 汽车→客货运输、教育局→教育)。**审 gold 时按"命中通名→分类"聚合**最容易抓这种系统性错,再在 override 纠正(已加 `局→政府及管理机构` 修一类)。

## 6. 文件地图

```
addr/            引擎(每文件单一职责;见 §4)
  normalize.py segment.py tongming.py disambiguate.py gazetteer.py menpai.py arbitrate.py
  classify.py  cli.py  categories.py  types.py  build_dict.py(离线生成auto词典)
dict/            tongming.auto.yaml(生成) tongming.override.yaml(手工) modifiers/levels/gazetteer/denylist.yaml
eval/            run_eval.py(回归评测)  regression.jsonl(逐行 {"name","address","label"})
tests/           pytest;每模块一份,33 passed
docs/
  HANDOFF.md(本文件)
  superpowers/specs/2026-06-15-...-design.md    (设计 spec)
  superpowers/plans/2026-06-15-...redesign.md   (14 任务实现计划)
data/input/      地址_625/4555/5000/6000.xlsx(语料,不进生产)
data/output/     运行产物(未纳入git):重做_4555.xlsx、抽样标注_对照表.xlsx
categories.xlsx  分类体系(列:分类名称/分类级别/向量匹配分类描述[含"适用对象"和"层级路径"])
```

## 7. 常用命令

```bash
pytest -q                                              # 全部测试(应 33 passed)
python3 -m addr.cli --input data/input/地址_4555.xlsx --output data/output/out.xlsx
python3 -m eval.run_eval eval/regression.jsonl        # 回归集准确率+错例
# categories.xlsx 改了之后重建 auto 词典:
python3 -c "from addr.build_dict import build_tongming_auto as b; from addr.categories import load_catalog as l; b(l('categories.xlsx'),'dict/tongming.auto.yaml')"
```

## 8. 迭代工作流(无真值集 → 这样长词典)

1. 跑 cli → 输出有 `置信`(gold/silver/review)和 `需复核` 列。
2. 抽查:**gold 段最重要**(生产直接采用);用"命中通名→分类"聚合抓系统性错。
3. 纠错 → 改 `dict/*.yaml`(**优先改词典,不改代码**);把确认正确的样本 `{name,address,label}` 追加进 `eval/regression.jsonl`。
4. 重跑 `eval` 守住不回退。
5. **批量改词典必有回退风险**——每次都要在标注集/回归集上验证(见 §10 教训)。

生成抽样标注表的脚本思路(可复用):分层抽 gold/silver/review,列含 引擎判定/置信/命中通名/理由 + 两列下拉(对?[对/错]、正确分类[引用"分类清单"sheet 全量类名]);行按 置信+分类聚类,便于人工快速核对。用户偏好**用 1/0 代替 对/错**,最后一列可能是用户自拟分类(未必是规范类名)。

## 9. 当前状态(真实测量)

- 测试:`pytest -q` → 33 passed。
- **首次真实标尺**(用户手工标 `data/output/抽样标注_对照表.xlsx` 200 抽样中的 160):
  - **gold 93.3%**(112/120)← 最关键、可信的数字
  - silver 72.5%(29/40);review 段用户未标(=待复核,无答案)
  - 整体(gold+silver)88.1%
- 据标注反馈修了一批后,标注集上升到 gold 99.2%/整体 96.9%,**但这是过拟合到该 160 条的乐观值,不代表泛化**。真实泛化必须**抽新样本**重测。
- 4555 语料分布:**待复核 ~29%**(诚实"判不出")、gold 可直接用 ~55%、其他服务 0%。(初版待复核 70%,经门牌规则+~150 业态通名覆盖降到 29%。)

## 10. 已知问题 / 待办(按优先级)

1. **未解决的回退 bug**:`华润置地广场写字楼-地下停车场(出入口)` 现判 **地铁站出入口**(应 地下停车场)。诡异点:单独 `main_entity` 得到 entity="华润置地广场写字楼-地下停车场"、`candidates` 首位是"地下停车场",但 `classify_one` 整体却输出"地铁站出入口"——说明 `classify_one` 内部某处(extract_primary 的弱通名过滤?modifier?候选重排?)与单测路径不一致。**接手第一件事建议:在 classify_one 里逐步打印 entity/primary/mcat/cands/ordered 复现定位。** 另两处回退(`LF女装生活馆`→服装鞋帽店、`城东建材家居批发大市场`→家居用品)其实更合理,可不算错。
2. **真实泛化准确率未知**:在 625/4555 之外**另抽一份新样本**人工标注当**留出测试集(永不用于调词典)**,才能得到可信数字并防过拟合。
3. **剩余 29% 待复核的硬尾巴**:纯品牌名(吸优剪/唤醒你的味蕾/丰巢…→需 `dict/gazetteer.yaml` 品牌词典)、无业态的裸"中心"、长尾零散业态。继续压收益递减且增加"自信错"风险——**自信错(gold 里的错)比待复核危害大,要优先控**。
4. **denylist 基本未生效**:候选只从"名称"主体来(不看地址),"银行对面"类噪声本就进不了候选,所以 `dict/denylist.yaml` 现阶段作用很小,别依赖它。
5. **gov_level 不改主分类**:若用户希望"X厅/局"主分类直接是"省级/区县级政府机关"(而非二级"政府及管理机构"),需在 classify_one 里对真正的政府机关(厅/局/委/政府,非事业单位中心/院)做"升级到 gov_level 三级"的逻辑——注意别误升事业单位(会打破"气象灾害防御技术中心→政府及管理机构"用例)。

## 11. Git / 工作流约定

- 分支:已在 `main`(重做已 merge 回本地 main)。**本地领先 origin/main 很多提交,未推送**。
- 用户规矩:**本地改+提交可以,但推送 GitHub(konjaku/AddressClassifier)前必须问用户**。
- 提交信息结尾附 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
- 别提交 `data/output/*.xlsx` 运行产物。
