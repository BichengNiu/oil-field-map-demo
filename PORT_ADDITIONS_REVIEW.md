# 港口补充与经营状态字段移除（2026-10-16）

已在原 132 条归档目录基础上新增 39 条，发布后原始目录 171 条；厄立特里亚继续排除，页面范围为 11 国、170 条港口及终端 ID。统计粒度是来源节点，并非互不重叠的天然港湾。

## 落实内容

- PortWatch 目录查询改为整个 11 国的国家条件，不再用 AIS/海域矩形截断埃及、也门海岸。已知 12 个遗漏统计节点接入既有日度采集与 2019 年起历史完整性校验。
- 26 个未对应 WPI 参考条目中，10 个明确联接到上述 PortWatch ID，余下 16 个作为无独立统计的目录节点。已联接条目不另外建立 WPI 副本。
- 另补入 11 个有具名来源的港口：塔朱拉、古贝特、索科特拉（豪拉夫）、吉赞工业港、阿布弗卢斯、阿布基尔、阿里什、加尔古卜、贝雷尼斯、阿斯塔拉、费雷敦凯纳尔。
- 共 12 条新增节点有独立统计资格，27 条只补目录，不填零、不借用邻港统计。目录是否有独立统计与当前经营状态无关。
- 移除港口表及 CSV 列“经营状态”、地图弹窗“运行状态”，删除最近七天推定正常的加工逻辑和状态标签函数。当前读写目录剔除该字段族，旧审计文档留存原始证据。
- Streamlit 仍只读 DuckDB；新资料由既有唯一发布脚本导入。未添加刷新按钮、任务或第二个数据库。

## 新增清单

| ID | 名称 | 国家 | 水域 | 类型 | 独立 PortWatch 统计 |
|---|---|---|---|---|---|
| port191 | 萨法加港（Safaga） | Egypt | 红海 | 综合商港 | 是 |
| port2044 | 德凯拉港（El Dekheila） | Egypt | 地中海 | 综合商港 | 是 |
| port2129 | 西迪基里尔终端（Sidi Kerir） | Egypt | 地中海 | 油品港及终端 | 是 |
| port2130 | 拉斯加里卜港（Ras Gharib） | Egypt | 苏伊士湾 | 油品港及终端 | 是 |
| port2131 | 宰特湾终端（Zeit Bay） | Egypt | 苏伊士湾 | 油品港及终端 | 是 |
| port2132 | 拉斯舒凯尔港（Ras Shukheir） | Egypt | 苏伊士湾 | 油品港及终端 | 是 |
| port2263 | 希赫尔石油终端（Ash Shihr） | Yemen | 亚丁湾 | 油品港及终端 | 是 |
| port2264 | 鲁杜姆终端（Rudum Terminal） | Yemen | 亚丁湾 | 油品港及终端 | 是 |
| port23 | 亚历山大港（Alexandria） | Egypt | 地中海 | 综合商港 | 是 |
| port2392 | 也门液化天然气终端（Yemen LNG Terminal） | Yemen | 亚丁湾 | 液化天然气港（LNG） | 是 |
| port2482 | 埃及液化天然气终端（Egyptian LNG Terminal） | Egypt | 地中海 | 液化天然气港（LNG） | 是 |
| port27 | 穆卡拉港（Mukalla） | Yemen | 亚丁湾 | 综合商港 | 是 |
| wpi45163 | 马阿迪亚港（El Maadiya） | Egypt | 地中海 | 地方及服务港 | 否 |
| wpi45175 | 哈姆拉石油终端（El Hamra Oil Terminal） | Egypt | 地中海 | 油品港及终端 | 否 |
| wpi45180 | 马特鲁港（Mersa Matruh） | Egypt | 地中海 | 地方及服务港 | 否 |
| wpi47960 | 努韦巴港（Nuwaybi'） | Egypt | 亚喀巴湾 | 综合商港 | 否 |
| wpi47970 | 库赛尔港（Al Qusayr） | Egypt | 红海 | 干货港 | 否 |
| wpi47974 | 哈姆拉温港（Hamrawein） | Egypt | 红海 | 干货港 | 否 |
| wpi47982 | 图尔港（At Tur） | Egypt | 苏伊士湾 | 综合商港 | 否 |
| wpi47987 | 宰提亚锚地（Marsa az Zaytiyah） | Egypt | 苏伊士湾 | 油品港及终端 | 否 |
| wpi47988 | 沙姆沙伊赫港（Sharm El Sheikh） | Egypt | 红海 | 客运旅游港 | 否 |
| wpi47989 | 宰特湾液化石油气终端（Zeit Bay Lpg Terminal） | Egypt | 苏伊士湾 | 液化石油气港（LPG） | 否 |
| wpi47990 | 赫尔格达港（El Ghardaqa） | Egypt | 红海 | 客运旅游港 | 否 |
| wpi48025 | 拉斯巴德兰石油终端（Ras Badran Oil Terminal） | Egypt | 苏伊士湾 | 油品港及终端 | 否 |
| wpi48057 | 扎法拉纳终端（Zafarana Terminal） | Egypt | 苏伊士湾 | 油品港及终端 | 否 |
| wpi48060 | 拉斯阿布宰尼马港（Ras Abu Zanimah） | Egypt | 苏伊士湾 | 干货港 | 否 |
| wpi48065 | 瓦迪费兰终端（Wadi Feiran） | Egypt | 苏伊士湾 | 油品港及终端 | 否 |
| wpi48198 | 尼什通港（Nishtun） | Yemen | 阿拉伯海 | 综合商港 | 否 |
| facility_tadjourah | 塔朱拉港（Port of Tadjourah） | Djibouti | 亚丁湾 | 综合商港 | 否 |
| facility_ghoubet | 古贝特港（Port of Ghoubet） | Djibouti | 亚丁湾 | 干货港 | 否 |
| facility_socotra | 索科特拉港（豪拉夫）（Socotra Port (Hawlaf)） | Yemen | 阿拉伯海 | 地方及服务港 | 否 |
| facility_jcpdi | 吉赞基础及下游工业港（Jazan City for Primary and Downstream Industries Port） | Saudi Arabia | 红海 | 综合商港 | 否 |
| facility_abu_flous | 阿布弗卢斯港（Abu Flous Port） | Iraq | 阿拉伯河 | 干货港 | 否 |
| facility_abu_qir | 阿布基尔港（Abu Qir） | Egypt | 地中海 | 干货港 | 否 |
| facility_arish | 阿里什港（Al Arish） | Egypt | 地中海 | 综合商港 | 否 |
| facility_gargoub | 加尔古卜港（Gargoub Port） | Egypt | 地中海 | 综合商港 | 否 |
| facility_berenice | 贝雷尼斯港（Mina Baranis (Port Berenice)） | Egypt | 红海 | 综合商港 | 否 |
| facility_astara | 阿斯塔拉港（Astara Port） | Iran | 里海 | 综合商港 | 否 |
| facility_fereydunkenar | 费雷敦凯纳尔港（Fereydunkenar Port） | Iran | 里海 | 综合商港 | 否 |

## 证据与限制

每条记录的来源 URL、坐标来源、位置精度、业务描述、统计资格及 WPI 对应关系见 [补充数据](PORT_ADDITIONS_2026-10-16.json)。原始国家查询见 [PortWatch 响应](audits/port_scope_portwatch_reference_2026-10-16.json)。

古贝特和塔朱拉使用具名港区多边形的代表点；阿斯塔拉、费雷敦凯纳尔使用具名 harbour 节点，区别于同名城市、邻国同名港或邻近游艇码头。数据归属 OpenStreetMap contributors，许可 [ODbL 1.0](https://www.openstreetmap.org/copyright)。索科特拉采用港务公司页面的嵌入地图点；其他官方目录补充使用航路指南的分钟精度港口代表点，加尔古卜使用 UKHO 港口入口灯标位置，不宣称精确泊位边界。

Ras Abu Aboud、Damerjog 及 RAK Maritime City/Saqr 的身份、开发阶段或父子范围仍未明确，未编造新节点；不能把本轮已知缺口补录解释为任何渔港、军港和私有码头均已穷尽。

采集与 LFS 发布结果以实际脚本退出码及发布提交为准。


## 2026-10-17 后续补录

另补九处目录，当前归档180条、展示179条；九处无独立日度统计。法拉桑、阿曼迪巴、利马、沙纳使用 OSM 渡轮节点及具名航线端点，来源为 OpenStreetMap contributors、ODbL 1.0；阿联酋迪巴、伦格及马西拉希尔夫采用 NGA 港口代表点；塔巴采用政府公布边界点平均值。达梅尔乔格仅补目录及资料，坐标未确定，不画推测点。详情见 `COVERAGE_RECHECK.md` 与本轮逐条审计；上文170条为此前发布基线。
