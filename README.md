# 中东油气资产与港口日活动地图

运行：`pip install -r requirements.txt && streamlit run app.py`

地图保留原油气资产图层，新增波斯湾、阿曼湾、霍尔木兹海峡、苏伊士运河和曼德海峡附近的港口图层。港口点位来自 [IMF PortWatch 港口数据](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports/FeatureServer/1)，每日船次与装卸货量来自 [PortWatch 每日港口活动](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0)。日期可选，默认该数据源的最新可用日期；API 结果缓存一小时，港口目录缓存一天，可在侧栏刷新。

“附近”使用 `portwatch.py` 中公开列出的五个经纬度框，以港口中心点判断。交叠区域按字典顺序分配，每个港口只出现一次。这涵盖**PortWatch 数据库在这些框内收录的全部港口**，不代表海岸线上所有港口、泊位和油码头；范围可直接在 `REGIONS` 中调整。

## 口径

| 地图字段 | 口径 |
| --- | --- |
| 油轮 / 其他货轮艘次 | 当日港口挂靠次数，艘次/日；货轮 `cargo` 不含 `tanker` |
| 卸货、装货、装卸合计 | PortWatch 依据 AIS/吃水变化估算的货量，公吨/日；页面除以 10,000 后显示为万吨/日 |
| 油轮载货原油当量估算 | `(import_tanker + export_tanker) × 桶/吨系数 ÷ 10,000`，单位万桶/日；默认系数 7.33，可在侧栏修改 |

**桶数不是已核实的原油吞吐量。** 油轮船型可能运输原油、成品油或其他液体货物，PortWatch 的这一汇总字段没有分油种。精确到油品的港口日吞吐桶数需要另接分货种的港口记录或商业船货数据。无当日记录显示缺报，不按零处理；有记录且数值为零才显示零。装卸合计是双向货量，不是净进口、净出口，也不能跨转运港直接求和当作区域贸易量。

PortWatch 的数据与覆盖变化、AIS 限制请参见其[数据与方法](https://portwatch.imf.org/pages/data-and-methodology)。霍尔木兹区域尤其需要留意信号干扰或关闭 AIS 对短期观测的影响。
