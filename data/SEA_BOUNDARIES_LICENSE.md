# 四海域边界来源

Flanders Marine Institute (2018). **IHO Sea Areas, version 3**.
https://doi.org/10.14284/323

官方元数据：https://www.vliz.be/en/imis?dasid=5444&module=dataset

通过 Marine Regions 的 `MarineRegions:iho` WFS，于 2026-10-06 提取波斯湾、红海、阿曼湾及亚丁湾四项多边形；原始 WFS 响应 SHA256 及 MRGID 保存在 `sea_boundaries.geojson`。只添加中文名称与来源说明，没有修改多边形坐标。查询框的外扩和事件检测的边界缓冲由代码完成，不代表修改官方海域定义。

该边界数据及此四区摘录适用 **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International**：https://creativecommons.org/licenses/by-nc-sa/4.0/ 。保留署名、非商业和相同方式共享要求。本许可仅适用于这份边界数据，不替代项目中其他来源各自的许可。
