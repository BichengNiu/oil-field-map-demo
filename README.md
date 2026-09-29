# 中东能源保供监测地图

运行：`pip install -r requirements.txt && streamlit run app.py`

## 当前功能

- 地图保留油气资产和重点港口，并增加苏伊士运河、曼德海峡、霍尔木兹海峡三个关键咽喉点。咽喉点固定读取 PortWatch 最新可用日，在橙色点位 popup 中显示总通过船舶数、估算承载货量，以及集装箱、干散货、普通货物、滚装、油轮/液货五类分项。
- 港口 popup 和“港口活动”表提供港口活动指数、船型结构、活跃天数率、单船平均货量、进出口平衡指数和风险运力，同时保留最新日有效进港艘次和估算装卸量。
- 地图模式支持“全部图层、仅港口与咽喉点、仅咽喉点、仅油气资产”。港口支持水域、名称、国家、日期及 7/30 天窗口筛选；资产支持名称、国家、层级、状态、类型和指标口径筛选。
- 底图使用 Esri 英文街道图，另可切换浅色图和卫星影像。港口点按窗口日均进港艘次缩放，咽喉点按最新日通过船数缩放；地图名称采用中文或英文，不依赖当地语言底图标注。
- 港口目录、日活动、窗口指标、风险运力和咽喉点请求分别缓存；侧栏可一键刷新。`app.py` 会检查 `portwatch.py` 模块版本，避免热重载遗留旧模块导致函数缺失。

## 数据范围

港口点位来自 [IMF PortWatch 当前港口数据库](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports_database/FeatureServer/0)，每日港口船次及装卸量来自 [每日港口活动](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0)。项目用 `portwatch.py` 中五个公开经纬度框定义波斯湾、阿曼湾、霍尔木兹海峡、苏伊士运河和曼德海峡“附近”，交叠区域按字典顺序唯一归属。它覆盖 PortWatch 数据库落入这些范围的全部唯一港口点，不等于当地全部实际泊位、油码头或未被 PortWatch 收录的设施。

咽喉点目录及每日通行数据分别来自 [PortWatch 咽喉点数据库](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_chokepoints_database/FeatureServer/0) 与 [每日咽喉点活动](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0)。港口日期和咽喉点日期独立显示，避免把更新节奏不同的数据强行对齐。

截至本次复核，当前港口点位源包含 2,065 个港口，项目五区筛出 63 个唯一港口；最新港口日活动为 2026-09-18，63 个港口均有当日记录。三个咽喉点最新日活动为 2026-09-20。数据会随源站更新，应用默认读取实时最新可用日期。

## 指标口径

| 指标 | 计算 | 解释 |
| --- | --- | --- |
| 港口活动指数 | 当前 7/30 日窗口有效进港艘次 ÷ 前一等长窗口艘次 × 100 | 100 表示持平；基期为 0 或任一窗口不完整时留空 |
| 船型结构 | 窗口内各船型进港艘次 ÷ 全部进港艘次 | 五类占比在有活动且数据完整时合计为 100% |
| 活跃天数率 | 窗口内进港艘次大于 0 的天数 ÷ 窗口天数 × 100% | 衡量活动连续性，不以单日零值替代趋势 |
| 单船平均货量 | 窗口内估算进口量与出口量之和 ÷ 有效进港艘次 | 单位万吨/艘次，属于 AIS、吃水和载重能力估算 |
| 进出口平衡指数 | `(出口量 − 进口量) ÷ (出口量 + 进口量) × 100` | −100 为完全进口导向，+100 为完全出口导向 |
| 风险运力 | 该港所有出港航线 `daily_capacity_at_risk` 合计 | 单位万吨/日；基于 2019—2024 航线网络的历史冲击暴露，不是实时船位 |

PortWatch 的 `portcalls` 是进入港界并满足其贸易挂靠筛选的有效进港艘次，不是在港船舶存量，也不能直接还原离港数或平均停泊时长。单日 0 表示源表当日确实记录为 0；缺报、窗口不完整和不可计算值保持为空。`tanker` 可能包含原油、成品油和其他液体货物，不应解释为分油种实测吞吐量。

## 复核与导出

运行 `python audit_ports.py` 可重新生成逐港原始日值及 7/30 日核查表。应用的“港口活动”页可下载当前筛选结果 CSV；“数据与方法”页列出边界框、公式、API 和限制。

PortWatch 方法说明：[Data and Methodology](https://portwatch.imf.org/pages/data-and-methodology)。
