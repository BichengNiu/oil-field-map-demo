# 港口类型

类型随代码版本维护在 `port_types.py`，显示和 CSV 导出使用同一转换。原始港口名称、统计 ID 和历史数据保持原样，页面不联网。

2026-10-16 核实：

| 港口 | 分类 | 证据 |
| --- | --- | --- |
| 杰贝阿里港（Jebel Ali），port744 | 综合港 / 集装箱枢纽 | [DP World 官方港口页](https://www.dpworld.com/en/ports-terminals/uae/jebel-ali-port)：大型集装箱港，同时提供干散货、液体散货及滚装服务。 |
| 富查伊拉港（Fujairah），port362 | 综合港 / 油品枢纽 | [富查伊拉港官方页](https://fujairahport.ae/)：多用途港、加油枢纽，业务包括 Oil、Dry Bulk、Container、General Cargo、RoRo；[Fujairah Terminals](https://www.fujairahterminals.ae/) 进一步确认集装箱、杂货及滚装服务。 |

其他分类仅采用当前快照保存的港口/WPI 原名中明确的 Oil Terminal、Crude Terminal、Refined Product Terminal、LNG Terminal、LPG Terminal、Gas Tanker Terminal。目录依据是已存入数据库的 `port_inventory_wpi_2026-09-30.json` 及逐港来源；原始 NGA 下载链接此次返回 403，因此未声称更新了 WPI 资料。此规则只确认设施类别，不推断枢纽排名或完整货种组合。

当前 132 个港口中，21 个可据以上证据分类，111 个暂列“待核实”。近期到港船型、零到港量和经营状态均不用于推断港口类型。
