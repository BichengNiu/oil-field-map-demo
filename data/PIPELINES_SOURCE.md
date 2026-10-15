# 输油管线路线与来源

数据由 Global Energy Monitor（GEM）的 Global Oil Infrastructure Tracker 提供。

- 固定来源：[官方地图数据](https://github.com/GlobalEnergyMonitor/goit-ggit-data-ops/blob/1f9ebdec2a863b7e0b6e9f4aa1edd666ec258667/goit_map_latest.geojson)，提交时间 2026-10-15 12:49:58 UTC。
- 来源为 GEM 研究地图导出，不是实时运行监测；每段保留 `LastUpdated`、原始状态、公开运力、单位、路线精度及 GEM 项目编号。缺失信息不补估计值，运力不等于实际流量。
- 许可：© Global Energy Monitor，[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)，依据 [GEM 官方许可声明](https://globalenergymonitor.org/creative-commons-license)。不暗示 GEM 认可本应用；原资料不保证完整或精确。
- 选取与沙特、伊拉克、伊朗、阿联酋、埃及、阿曼、科威特、卡塔尔、也门、叙利亚、土耳其、以色列、约旦、黎巴嫩、巴林有关的 `Fuel=Oil` 路线。跨境线路保留全线，因此也涉及邻国。排除 NGL 和天然气；不是各国完整管网。
- 共 250 个独立 ProjectID，涉及 182 个管线系统名称。分段运力不相加为系统运力；同一走廊不同分段、并行线或规划替代线不是重复记录。
- 修改：部分名称译为中文；以 0.003 度容差做几何简化，保留 MultiLineString 分支结构，未跨空缺连接，未推测路线。坐标仍为 GeoJSON 的 WGS84 `[经度,纬度]`。低精度和示意线路即使状态为运行中，也显示为虚线。
- 地图实线为资料记载运行中且源精度中等以上；长虚线为建设或规划；短虚线为停用、搁置、取消等。所有状态及路线精度可点击查看，不能据线型判断实时通油。

归档文件 `oil_pipelines.geojson` 的 metadata 包含来源 URL、固定提交、原文件 SHA256、许可和修改说明。下载固定来源到本地后，可用 `python build_pipeline_data.py /path/to/goit_map_latest.geojson` 重建；该工具不会自动运行或另建定时任务。

发布端通过既有 `snapshot_update.py --publish` 将文件导入唯一 DuckDB 快照并校验。Streamlit 只从该快照的 documents 表读取，不在载入或勾选图层时联网下载管线。
