# 输油管线路线与来源

数据由 Global Energy Monitor（GEM）的 Global Oil Infrastructure Tracker 提供。

- 固定来源：[官方地图数据](https://github.com/GlobalEnergyMonitor/goit-ggit-data-ops/blob/1f9ebdec2a863b7e0b6e9f4aa1edd666ec258667/goit_map_latest.geojson)，提交时间 2026-10-15 12:49:58 UTC。
- 来源为 GEM 研究地图导出，不是实时运行监测；每段保留 `LastUpdated`、原始状态、公开运力、单位、路线精度及 GEM 项目编号。缺失信息不补估计值，运力不等于实际流量。
- 许可：© Global Energy Monitor，[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)，依据 [GEM 官方许可声明](https://globalenergymonitor.org/creative-commons-license)。不暗示 GEM 认可本应用；原资料不保证完整或精确。
- 选取与沙特、伊拉克、伊朗、阿联酋、埃及、阿曼、科威特、卡塔尔、也门、叙利亚、土耳其、以色列、约旦、黎巴嫩、巴林有关的 `Fuel=Oil` 路线。跨境线路保留全线，因此也涉及邻国。排除 GEM 的独立 NGL 分类和天然气；Oil 是来源分类，本身不能证明每条线只输送纯原油，不能据此推断混输细节；不是各国完整管网。
- 共 250 个独立 ProjectID，涉及 182 个管线系统名称。分段运力不相加为系统运力；同一走廊不同分段、并行线或规划替代线不是重复记录。
- 修改：所有管线名称补齐项目中文译名，展示为中文（英文）；以 0.003 度容差做几何简化，保留 MultiLineString 分支结构，未跨空缺连接，未推测路线。坐标仍为 GeoJSON 的 WGS84 `[经度,纬度]`。精度保留在资料弹窗中，按用户最新要求不另用第三种线型表示精度。
- 地图只用两种线型：实线为资料记载运行中，统一长虚线为建设、规划、闲置、退役等其他状态。所有状态及路线精度可点击查看，不能据线型判断实时通油。

归档文件 `oil_pipelines.geojson` 的 metadata 包含来源 URL、固定提交、原文件 SHA256、许可和修改说明。下载固定来源到本地后，可用 `python build_pipeline_data.py /path/to/goit_map_latest.geojson` 重建；该工具不会自动运行或另建定时任务。

发布端通过既有 `snapshot_update.py --publish` 将文件导入唯一 DuckDB 快照并校验。Streamlit 只从该快照的 documents 表读取，不在载入或勾选图层时联网下载管线。

## 2026-10-16 运力与覆盖核查

逐个 ProjectID 对照固定源表的国家字段以及起终点国家字段，250个应导入分段均已导入，没有漏导、额外分段或重复主键。逐段复核显示几何与原始几何的距离偏差不超过声明的0.003度简化容差，未丢失分支。

这不等于所有国家实际管网完整覆盖。GEM 的2026-06-18研究备忘明确列出缺少几何的 Tal Adas–Tartus、Khor Al-Amaya terminal line、Goreh B–Genaveh 在建馈线及两项 East–West 扩容分段；当前固定地图导出没有这些具名路线。主线已映射的扩容项目不一定需要新路线。无可靠几何时不画推测线；250段中116段源精度为低或示意，保持虚线。出处及边界见 `pipeline_capacity_review.json` 的 coverage。

对全部162个具名 GEM.wiki 来源链接做访问并重试：133个可读，29个仍返回403；访问失败不能当作没有资料。源表125段缺运力，122段原单位为桶/日，3段为百万吨/年。只有桶/日可以精确除以1,000,000得到百万桶/日；质量与体积转换缺少密度时不采用 GEM 的桶油当量字段代替原油体积。

已执行的处理：

- 111段保留单一数值，均显示“百万桶/日”；其中包含源表记录，不能把数值同值对照解释为全部已独立证明当前可用。另1段 Ahwaz–Ray 按项目页保留0.45—0.6区间，不只取上限。
- SUMED 两条线撤回各1.25的平均分配假设，单线留空；EIA明确披露的系统总值2.5单独显示，两条线共享同一系统编号，不可重复累加。
- 沙特 East–West：EIA的基准标称值5与2019年历史临时扩容值7分别列示；不把临时最大值当成当前可用。ADCOP：EIA记载最大值1.8，与2020财报设计值1.5分开，不把二者当作同一口径。Goreh–Jask：EIA的有效值约0.3，区别于目标或实际流量。
- 8段存在分段、数值或指标口径冲突，地图撤下确定数值并显示待核实，原始数值仍保留在证据中。例如 Danan–Dehloran 的项目页引文实际上披露2018年油田产量，不能用作管线设计运力。
- 125段缺失值和3段质量单位继续留空，不补零。规划、停用等状态不会被解释成运行中的输送能力；全图没有“总运力”简单求和。

250条逐段记录与来源在 [pipeline_audit.csv](pipeline_audit.csv)，详细判断、源表值、访问状态、页面散列、短引文和原始来源在 [pipeline_capacity_review.json](pipeline_capacity_review.json)。GEM.wiki短引文按其 CC BY-NC-SA 4.0 署名；原始路线资料继续遵循 CC BY 4.0；EIA及运营商证据分别保留原始链接。

核查脚本：`python audit_oil_pipelines.py downloaded-goit.geojson --csv data/pipeline_audit.csv`。可执行检查及摘要见 `audits/pipeline_capacity_audit.ipynb`。页面同时校验管线与核查记录的版本散列及逐段判断；未经重建的核查改动会阻止发布，不能静默显示旧运力。


## 阿联酋连接复核与隔离

运营商 [ADNOC Gas](https://www.adnocgas.ae/en/our-operations/gas-processing)明确记载IGD项目连接达斯岛与哈布善，属于输气系统。独立归档同一GEM固定提交的 [GGIT源](https://github.com/GlobalEnergyMonitor/goit-ggit-data-ops/blob/1f9ebdec2a863b7e0b6e9f4aa1edd666ec258667/ggit_map_latest.geojson)，SHA256为`6b5fc679aa17ab37959b597095310f6dab996e48435fb4c580da7f7cf3dfaca4`，CC BY 4.0。`uae_gas_connections.geojson`仅选取3条相关源记录，不是完整气网。

海、陆示意分段P5683/P5711之间约22公里没有源坐标，保持分离；不能认定这两个分段就是运营商记载的两根完整管线。气线P5684从阿布扎比城区出发，与乌姆沙伊夫不符，不绘制。油线P0640的终点约54.5972E、24.4093N，明显不是达斯岛，暂停地图绘制。两条记录的源几何仍完整保留在归档中。原油归档250段，实际绘制249段；另绘制2段蓝灰色输气示意，不将气体能力换成原油百万桶/日。逐条证据见`uae_pipeline_connectivity_review.json`。

`bilingual_names.json`记录项目中文译名，源英文名及ProjectID不变。资产、港口、咽喉点双语字段写入发布快照并在发布前验证；源事实主键及历史原文保留。

## 有具名证据但没有路线几何的项目

`data/pipeline_projects.json` 单独记录阿联酋 ADNOC West-East Pipeline。ADNOC 2026-05-15 公告确认在建、预计2027年投产并使富查伊拉出口能力翻倍；没有公开独立运力和可核验线路坐标，均保持空值。此记录通过唯一发布脚本进入同一 DuckDB，不冒充 GEM 线条，不复用现有 ADCOP 几何，可在地图名称查找和图例项目入口打开资料。

## 2026-10-17 后续补证

上述2026-10-16结论保留为核查历史；低精度不再以第三种线型表示，统一按实际资料状态使用实线或长虚线。

- P0551 东西原油系统更新采用 [Aramco 2026年一季度公告](https://www.aramco.com/en/news-media/news/2026/aramco-announces-first-quarter-2026-results) 的最大运力 **7 百万桶/日**，旧EIA基准5与2019年临时值保存在 `previous_capacity_review`。这是更新已有系统证据，不新增推测线路，不作为实时输送量。
- `pipeline_projects.json` 再补豪尔阿迈耶终端线、古雷B—格纳韦馈线两项资料，连同阿联酋东西线共三项。伊拉克JICA资料为历史设施依据；伊朗GEM在建/规划证据不一致，当前状态均不强行判定，几何和独立运力保持为空。地图名称查找可打开资料，不能凭该入口认为已拥有真实路线。

最新展示规则（2026-10-17）：上述无几何项目仅保留来源归档，移除地图图例中的项目名称、搜索候选和打开项目弹窗的逻辑。只有已核验路线的管线才能成为地图对象；三项项目的公开公告及端点名称不足以代替连续坐标，未画示意连接线。
