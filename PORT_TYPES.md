# 港口类型逐项核查

## 应用筛选分类

港口类型收敛为 9 个互斥大类，详细业务描述独立保留在列表及 CSV 的“业务特点”列。
按稳定目录 ID 显式归类，不由名称关键词、进港量、船型占比或设施邻近关系推断。
逐港对应关系见 [分类映射](audits/port_type_groups_2026-10-16.json)；以下原始核查表的“类型”为完整业务描述，不覆盖或删除。

| 港口类型 | 港口数 |
|---|---:|
| 综合商港 | 52 |
| 集装箱港 | 1 |
| 干货港 | 8 |
| 油品港及终端 | 41 |
| 液化天然气港（LNG） | 2 |
| 液化石油气港（LPG） | 3 |
| 油气综合港 | 3 |
| 客运旅游港 | 3 |
| 地方及服务港 | 17 |
| 待核实 | 2 |

杰贝阿里、富查伊拉保持综合商港分类，分别在业务特点保留集装箱枢纽、油品枢纽描述。
工业属性、海上/陆岸形态、进口/出口方向和项目状态不再单独拆出筛选类型。
`wpi48035` 只证实气体船码头，不能据此区分 LNG/LPG；`wpi48533` 只证实液体装卸终端，货种未明确。
两处继续显示已经核实的业务描述，主分类暂列“待核实”，不猜测其为油品或混合油气港。

## 业务特点核查

2026-10-16 已逐一检查当前快照的 **132 个目录 ID**，全部提供有来源支持的类别。**128 项有较明确的业务/设施类别，4 项仅采用来源明确支持的宽泛类别**；后者不代表完整货种清单或具名身份已查清。

应用与 CSV 使用 `port_types.py` 的同一 ID 映射。原始名称、统计 ID、坐标和历史数据不改动；新增未知 ID 保持“待核实”，不再靠名称关键词或 AIS 到港构成自动猜分类。

分类是目录属性，不是实时营业状态。指南版本、存档捕获日与本次复核日分别保存，不能将历史设施描述、项目计划或零进港量当作当前停复运证明。原有 2026-10-16 两港官方复核已纳入这次完整复核。

## 证据与方法

- 使用 38 个来源：港务局、运营商、政府航路指南及部分船代技术目录。完整 URL、获取时间、原文 SHA-256（FSO 目录响应保存件注明校验范围）、PDF 页码和逐港摘录见 [审计数据](audits/port_type_review_2026-10-16.json)。
- NGA Pub.172 为 2025 版，校正至 2025-08-30；Pub.132 为 2026 版。PDF 链接的 `#page` 为文件页码。
- 伊朗港务机构、Mwani Qatar、Asyad 的部分实时网站拒绝访问时，采用其官方网页的可读取存档，并保留实际捕获日期；没有把 200 状态的拒绝页、404 页或搜索摘要当作证据。
- 不由设施邻近关系推定业务、从港群推定每一子码头的全部能力，也不由近期船型比例判定枢纽属性。油品、LNG、LPG、渔港、邮轮港、社区港、工业/商用复合港与项目分别处理。

## 来源限制及纠正

| ID | 处理 |
| --- | --- |
| `facility_wpi48104` | 指南只证实小型附属港及靠泊设施，未公布完整货种；不推断为油品港或大型综合港。 |
| `port1342` | 原统计 ID 关联 Doha、Umm Said 两个 WPI 项，属于复合范围；不能视作单一旧多哈邮轮码头。 |
| `port2245` | 只确认油品储运类型；不将指南内旧 FSO 船名或开工描述用作当前运营证明。 |
| `port2486` | 依据该 WPI 所在的贾斯克沿海港区分类；没有将其自动等同较远处新建的原油出口终端。 |
| `port306` | 原统计 ID/WPI 含 Dubai Creek、Mina Rashid 及干船坞港区；不只代表邮轮码头。 |
| `port5` | PortWatch/WPI Abu Zaby 范围包含 Mina Zayed；与另列扎耶德设施可能重叠，不新增统计或重复合计。 |
| `wpi48268` | WPI 48268 源目录写 Mubarraz，NGA 相同编号写 Mubarek；类别均为海上油品装卸，具名身份冲突另记，不改原始 ID/名称。 |
| `wpi48341` | NGA 五座码头与船代一个泊位的口径不同；这里只确认一般货船业务，不合并或重写泊位数。 |
| `wpi48404` | WPI 编号 48404 与指南所列 48004 不一致，名称及30°11N/47°54E位置相符；以名称、位置和船代目录交叉核对，保留原 ID。 |
| `wpi48406` | 源目录名称为 LNG，NGA §16.51 明确为 LPG 两泊位及油轮一泊位；按设施业务纠正类型，保留原始名称/ID，不将 LPG 写为 LNG。 |
| `facility_shinas` | 本条目录坐标为所在地参考点；指南证实渔港及传统木船水道，不等同逐泊位业务清单。 |
| `facility_suwaiq` | 运营商资料确认项目货、牲畜与食品业务；坐标仍是目录中的沿海所在地参考点，不表示单一泊位。 |
| `facility_shahama` | 运营商把休闲游艇设施写作发展用途；不将规划设施宣称为全部建成。 |
| `facility_grand_faw` | 项目/设施类型，不据计划启用年份推定已商业投运。 |
| `fso151` | 仅核实上游明确命名的海上油品终端类别；没有公开具名设施对应关系，不推断运营商、油田或具体货种。 |
| `fso158` | 仅核实上游明确命名的海上油品终端类别；没有公开具名设施对应关系，不推断运营商、油田或具体货种。 |

沙尔马、希纳斯和两个未具名海上油品终端的 `verification` 为 `documented_broad_type`。这些条目只在已有证据范围内分类，不宣称已获得完整业务或身份资料。

## 全部目录

| ID | 港口 | 类型 | 依据 |
| --- | --- | --- | --- |
| `facility_wpi48104` | 沙尔马港（Sharmah） | 小型地方港（靠泊服务） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=111)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=112) |
| `port105` | 帕尔斯港码头（Bandar-E Pars Terminal） | 石化工业及物流港（固体、液体产品） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=274)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=275) |
| `port106` | 沙希德拉贾伊港（Bandar Shahid Rajaee） | 综合商港（集装箱、滚装、散货、油品） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=265)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=266) |
| `port1068` | 卡尔哈特液化天然气码头（Qalhat LNG Terminal） | 液化天然气出口终端（兼凝析油装卸） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=221)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=222) |
| `port107` | 阿巴斯港（Bandar Abbas） | 军商港区（商用泊位、海军设施） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=264)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=265) |
| `port108` | 霍梅尼港（Bandar Khomeini） | 河口综合商港（杂货、散货、集装箱、油品） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=404)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=405) |
| `port1088` | 米沙卜港（Ras Al Mishab） | 干货港（杂货、水泥散货） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=378)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=379) |
| `port1091` | 拉斯坦努拉港（Ras Tanura） | 油品出口港 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=366)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=367) |
| `port1203` | 西特拉港（Sitrah） | 油品码头（炼油产品装卸） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=347)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=348) |
| `port13` | 阿治曼港（Ajman） | 综合商港（集装箱、杂货、滚装） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=287)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=288) |
| `port1340` | 乌姆盖万港（Umm al Qaiwain） | 地方商港（中小型货船、传统木船） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=286)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=287) |
| `port1341` | 乌姆盖斯尔港（Umm Qasr） | 综合商港（集装箱、项目货、杂货、散货） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=393)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=394) |
| `port1342` | 多哈—乌姆赛义德港（Doha-Umm Said） | 复合港区（多哈商港、梅赛义德工业港） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=326)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=327)、[来源3](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=336)、[来源4](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=337) |
| `port18` | 荷台达港（Hudaydah (Hodeidah)） | 综合商港（杂货、油品） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=150)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=151) |
| `port196` | 布什尔港（Bushehr） | 综合商港（杂货、集装箱） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=397)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=398)、[来源3](https://web.archive.org/web/20211129024157/https://www.pmo.ir/en/portsandterminals/iranianports/bushehrport) |
| `port20` | 巴士拉港（Al Basrah） | 内河商港（杂货、仓储） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=416)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=417) |
| `port2012` | 哈利法·本·萨勒曼港（Khalifa Bin Salman） | 综合商港（集装箱、滚装、杂货、客运） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=347)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=348) |
| `port2026` | 哈马德港（Hamad Port） | 综合商港（集装箱、杂货、车辆、牲畜） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=325)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=326) |
| `port2060` | 萨勒曼港（Mina Salman） | 干货港（杂货、散货） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=347)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=348) |
| `port2067` | 舒艾拜港（Shuaiba） | 工业综合港（干货、石油产品） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=385)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=386) |
| `port2109` | 穆哈港（Mokha） | 沿海商港（杂货） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=152)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=153) |
| `port2164` | 哈尔克岛石油码头（Kharg Island） | 原油出口终端 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=399)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=400) |
| `port2165` | 拉万岛石油码头（Lavan） | 油品出口终端 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=273)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=274) |
| `port22` | 哈姆里亚液化石油气码头（Al Hamriyah LPG Terminal） | 液化石油气码头（兼粮食、杂货） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=286)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=287) |
| `port2217` | 哈夫吉港（Ras Al Khafji） | 油品装卸终端 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=379)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=380) |
| `port2219` | 萨利夫港（Salif） | 干散货港（盐、水泥等） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=147)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=148) |
| `port2235` | 吉尔库岛港（Zirku Island） | 海上油品装卸港（单点系泊） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=311)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=312) |
| `port2237` | 达斯岛港（Das Island） | 油气出口终端（原油、LNG、LPG） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=319)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=320) |
| `port2245` | 拉斯伊萨海洋码头（Ras Isa Terminal） | 油品储运终端 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=148)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=149) |
| `port226` | 恰巴哈尔港（Chabahar） | 综合商港（杂货、集装箱） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=247)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=248) |
| `port24` | 朱拜勒港（Jubail） | 工业及商业复合港（石化、散货、杂货） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=372)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=373) |
| `port2477` | 阿巴丹港（Abadan） | 炼油配套河港（沥青、杂货、船舶加油） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=412)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=413) |
| `port2478` | 巴里根角港（Bahregan） | 海上油品装卸终端 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=402)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=403) |
| `port2479` | 巴士拉石油码头（Basrah Oil Terminal） | 海上油品出口终端 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=408)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=409) |
| `port2486` | 贾斯克港（Jask） | 沿海港区（靠泊、海军设施） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=249)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=250) |
| `port2493` | 祖尔港（Mina Al Zour） | 油品装卸终端 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=381)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=382) |
| `port25` | 舒韦赫港（Shuwaikh） | 综合商港（杂货、集装箱） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=390)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=391)、[来源3](https://kpa.gov.kw/en/shuwaikh-port/) |
| `port275` | 达曼港（Dammam） | 干货综合港（集装箱、杂货、散货、滚装） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=360)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=361)、[来源3](https://www.iss-shipping.com/ports/dammam/) |
| `port294` | 吉布提港（Djibouti） | 综合商港（杂货、散货、航运服务） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=198)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=199) |
| `port306` | 迪拜港（Dubai） | 复合港区（杂货、滚装、邮轮、修船） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=291)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=292)、[来源3](https://www.dpworld.com/en/ports-terminals/uae/mina-rashid) |
| `port321` | 阿达比亚港（Al Adabiyah） | 综合商港（粮食、散货、杂货） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=32)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=33) |
| `port362` | 富查伊拉港（Fujairah） | 综合港 / 油品枢纽（石油储运、加油、干散货、集装箱等） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=233)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=234)、[来源3](https://fujairahport.ae/) |
| `port5` | 阿布扎比港（Abu Dhabi） | 综合港区（杂货、散货、邮轮） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=301)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=302)、[来源3](https://www.adports.ae/ports-terminals/commercial-ports/zayed-port/) |
| `port512` | 杰贝勒宰纳／鲁韦斯港（Jabal Az Zannah-Ruways） | 油品工业港（原油、炼化产品） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=313)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=314) |
| `port526` | 朱艾玛石油码头（Juaymah） | 海上油品出口终端 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=370)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=371) |
| `port561` | 豪尔费坎港（Khor Fakkan） | 集装箱转运港 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=237)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=238)、[来源3](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=307)、[来源4](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=308) |
| `port563` | 霍拉姆沙赫尔港（Khorramshahr） | 内河综合商港（杂货、集装箱） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=414)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=415) |
| `port71` | 苏伊士港（As Suways） | 运河门户综合港（货运、航运服务、修船） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=30)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=31) |
| `port72` | 沙迦港（Sharjah） | 综合商港（集装箱、杂货、散货、油品） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=289)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=290) |
| `port743` | 艾哈迈迪港（Mina Al Ahmadi） | 油品出口港 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=387)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=388) |
| `port744` | 杰贝阿里港（Jebel Ali） | 综合港 / 集装箱枢纽（集装箱业务突出，同时处理散货、液体货物和车辆） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=295)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=296)、[来源3](https://www.dpworld.com/en/ports-terminals/uae/jebel-ali-port) |
| `port745` | 卡布斯港（Port Sultan Qaboos） | 多用途港（客运、邮轮、货运泊位） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=224)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=225)、[来源3](https://web.archive.org/web/20250120090050/https://asyad.om/ports/oman's-ports/port-sultan-qaboos) |
| `port747` | 萨克尔港（Mina Saqr） | 综合港 / 干散货港（骨料、水泥、集装箱、油品） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=280)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=281) |
| `port828` | 苏赫纳港（El Sokhna） | 综合商港（集装箱、散货、液体货物） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=36)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=37) |
| `port9` | 亚丁港（Aden） | 综合转运港（集装箱、杂货、燃油补给） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=158)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=159) |
| `port988` | 苏哈尔港（Port of Sohar） | 综合工业港（矿石、集装箱、散货、液体货物） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=229)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=230) |
| `wpi47855` | 多哈雷港（Doraleh） | 复合港区（集装箱、油品码头） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=197)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=198) |
| `wpi47880` | 阿萨布港（Assab） | 综合商港（杂货、散货、油品） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=94)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=95) |
| `wpi48035` | 苏赫纳港气体船码头（Sokhna Port Gas Tanker Terminal） | 气体船专用码头 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=36)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=37) |
| `wpi48050` | 伊斯梅利亚港（El Ismailiya） | 运河服务港（引航、驳船） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=26)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=27) |
| `wpi48053` | 拉斯苏德尔港（Ras Sudr） | 海上油品码头 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=44)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=45) |
| `wpi48055` | 艾因苏赫纳码头（Ain Sukhna Terminal） | 油气储运终端（原油、LNG接收及再气化） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=38)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=39) |
| `wpi48255` | 法赫勒港（Mina Al Fahl） | 油品装卸港 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=226)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=227) |
| `wpi48259` | 哈萨卜港（Khawr Khasab） | 沿海地方港（本地船舶、交通） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=256)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=257) |
| `wpi48265` | 法特赫石油码头（Fateh Oil Terminal） | 海上原油装卸终端 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=306)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=307) |
| `wpi48268` | 穆巴拉兹石油码头（Mubarraz Oil Terminal） | 海上油品装卸终端 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=259)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=260) |
| `wpi48269` | 贾齐拉港（Al Jazeera Port） | 综合港（骨料、散货、液体、滚装、集装箱） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=284)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=285) |
| `wpi48272` | 沙迦海上码头（Sharjah Offshore Terminal） | 海上油品装卸终端 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=288)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=289) |
| `wpi48279` | 乌姆纳尔港（Umm An Nar） | 油品装卸码头（油轮业务） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=305)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=306)、[来源3](https://www.iss-shipping.com/ports/umm-al-nar/) |
| `wpi48280` | 哈莱拉石油码头（Hulaylah Oil Terminal） | 海上油品装卸终端 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=282)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=283) |
| `wpi48295` | 哈卢尔岛港（Jazirat Halul） | 海上油品储运港 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=338)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=339) |
| `wpi48298` | 阿尔沙欣码头（Al Shaheen Terminal） | 海上油品储卸终端（FSO） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=342)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=343) |
| `wpi48300` | 阿尔赖扬码头（Al Rayyan Terminal） | 海上油品储卸终端（FSO） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=342)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=343) |
| `wpi48310` | 麦纳麦港（Al Manamah） | 地方港（传统木船、驳运） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=357)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=358) |
| `wpi48341` | 拉斯盖尔港（Ras Al Ghar） | 地方商港（一般货船业务） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=372)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=373)、[来源3](https://www.iss-shipping.com/ports/ras-al-ghar/) |
| `wpi48342` | 朱艾玛液化石油气码头（Ju Aymah Lpg Terminal） | 液化石油气出口码头 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=371)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=372) |
| `wpi48360` | 阿卜杜拉港（Mina Abd Allah） | 油品出口码头 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=384)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=385) |
| `wpi48374` | 多哈港（Doha Harbor） | 沿海商港（传统木船、小型沿海船舶） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=392)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=393) |
| `wpi48390` | 阿迈耶港（Khawr Al Amaya） | 海上油品出口终端 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=407)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=408) |
| `wpi48440` | 霍斯罗阿巴德港（Khosrowabad） | 油品装卸码头 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=412)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=413) |
| `wpi48450` | 马赫沙赫尔港（Bandar-E Mahshahr） | 油品出口码头（炼化产品、原油） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=405)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=406) |
| `wpi48468` | 锡里斯石油码头（Sirus Oil Terminal） | 海上油品储卸终端（FSO） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=382)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=383) |
| `wpi48530` | 霍尔木兹岛港（Jazireh-Ye Hormoz） | 地方散货装运港（氧化铁、驳运） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=261)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=262) |
| `wpi48533` | 塔赫里海上码头（Bandar Taheri Offshore Terminal） | 海上液体装卸终端（单点系泊） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=275)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=276) |
| `wpi48535` | 锡里岛港（Jazireh-Ye Sirri） | 油品出口码头 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=260)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=261) |
| `port1081` | 拉比格港（Rabigh） | 油品码头（炼化产品装卸） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=123) |
| `port1089` | 拉斯海尔港（Ras Al-Khair） | 工业综合港（铝材、散装化工品、集装箱） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=376) |
| `port1090` | 拉斯拉凡港（Ras Laffan） | 天然气工业港（LNG、液体产品、配套物流） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=340)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=341)、[来源3](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=327)、[来源4](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=328) |
| `port1408` | 延布商业港（Yanbu (Yanbu city)） | 综合商港（干货、客运） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=116)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=117) |
| `port2074` | 吉赞港（Jazan） | 综合商港（杂货、集装箱、滚装、水泥） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=142)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=143) |
| `port2236` | 杰贝尔丹那港（Jebel Dhanna） | 油品出口终端（杰贝尔丹那港区） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=313)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=314) |
| `port304` | 杜巴港（NEOM）（Duba (Port of Neom)） | 综合商港（滚装、杂货） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=112)、[来源2](https://www.iss-shipping.com/ports/dhuba/) |
| `port305` | 杜巴油轮码头（Duba Bulk Plant Tanker Terminal） | 油品装卸码头 | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=112) |
| `port518` | 吉达港（Jeddah） | 综合商港（集装箱、干散货、客运） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=126)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=127)、[来源3](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=128) |
| `port519` | 舒艾拜港（沙特）（Shoaiba） | 电力工业专用港（燃油装卸） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=122) |
| `port570` | 延布法赫德国王工业港（Yanbu (King Fahd Port)） | 石化工业港（原油、成品油、液体产品） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=119)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=120)、[来源3](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=121)、[来源4](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=122) |
| `port746` | 塞拉莱港（Salalah） | 综合商港（集装箱、杂货、散货、液体货物） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=178)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=179) |
| `port984` | 杜库姆港（Duqm） | 综合工业港（杂货、散货、液体货物、船舶维修） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=185)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=186) |
| `wpi48404` | 祖拜尔港（Khawr Al Zubair） | 综合商港（杂货、油品、气体货物） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=394)、[来源2](https://www.iss-shipping.com/ports/khor-al-zubair/) |
| `wpi48406` | 祖拜尔液化天然气码头（Khawr Al Zubair Lng Terminal） | 液化石油气码头（兼油轮泊位） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=394) |
| `facility_shinas` | 希纳斯港（Shinas） | 沿海地方港（渔业、传统木船） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=233) |
| `facility_suwaiq` | 苏瓦伊克港（Suwaiq） | 地方综合商港（项目货、牲畜、食品） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=229)、[来源2](https://web.archive.org/web/20250120084129/https://asyad.om/ports/oman's-ports/port-suwaiq) |
| `port192` | 塞得港（Port Said） | 运河门户综合港（集装箱、杂货、航运服务） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub132bk.pdf#page=50)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub132bk.pdf#page=51)、[来源3](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub132bk.pdf#page=52) |
| `port274` | 达米埃塔港（Damietta） | 综合商港（集装箱、杂货、散货、液体货物） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub132bk.pdf#page=47)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub132bk.pdf#page=48)、[来源3](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub132bk.pdf#page=49) |
| `facility_delma` | 德尔马港（Delma Port） | 社区综合港（客运渡轮、货运、渔业） | [来源1](https://www.adports.ae/ports-terminals/community-ports/delma-port/) |
| `facility_freeport` | 自由港（扎耶德港区）（Free Port (Zayed)） | 近海服务港（小型货船、拖轮、驳船） | [来源1](https://www.adports.ae/ports-terminals/commercial-ports/free-port/) |
| `facility_mirfa` | 米尔法港（Mirfa Port） | 社区渔港（渔船、休闲船舶） | [来源1](https://www.adports.ae/ports-terminals/community-ports/mirfa-port/) |
| `facility_mugharraq` | 穆盖拉克港（Mugharraq Port） | 综合服务港（海上油气后勤、杂货、渡轮） | [来源1](https://www.adports.ae/ports-terminals/commercial-ports/mugharraq-port/) |
| `facility_musaffah` | 穆萨法港（Musaffah Port） | 工业综合港（杂货、散货、滚装） | [来源1](https://www.adports.ae/ports-terminals/commercial-ports/musaffah-port/) |
| `facility_shahama` | 沙哈马港（Shahama Port） | 社区多用途港（规划发展休闲游艇服务） | [来源1](https://www.adports.ae/ports-terminals/community-ports/shahama-port/) |
| `facility_sila` | 锡拉港（Sila Port） | 地方综合港（滚装、杂货、油气后勤、渔业） | [来源1](https://www.adports.ae/ports-terminals/commercial-ports/sila-port/) |
| `facility_zayed` | 扎耶德港（Zayed Port） | 综合商港（杂货、散货、邮轮） | [来源1](https://www.adports.ae/ports-terminals/commercial-ports/zayed-port/) |
| `port2025` | 哈利法港（Khalifa Port） | 综合商港（集装箱、滚装、散货、液体及气体） | [来源1](https://www.adports.ae/ports-terminals/commercial-ports/khalifa-port/) |
| `facility_bahrain_lng` | 巴林LNG进口码头（Bahrain LNG Import Terminal） | 液化天然气进口终端 | [来源1](https://www.mediaoffice.abudhabi/en/transport/noatum-maritime-part-of-ad-ports-group-signs-5-year-agreement-with-bapco-upstream-to-provide-marine-services-at-bahrain-lng-import-terminal/) |
| `facility_grand_faw` | 大法奥港（Al Faw Grand Port） | 深水综合港项目（集装箱码头） | [来源1](https://en.alfawport.gov.iq/container-terminal/) |
| `facility_rak` | 哈伊马角港（Ras Al Khaimah Port） | 综合商港（货运、仓储、邮轮） | [来源1](https://www.rakports.ae/ports/ras-al-khaimah-port/) |
| `facility_aljeer` | 杰尔港（Al Jeer Port） | 牲畜进口专用港（检疫、候泊） | [来源1](https://www.rakports.ae/wp-content/uploads/2026/04/marine-information-guide.pdf) |
| `facility_rashid` | 拉希德港（Mina Rashid） | 邮轮及多用途港（客运、滚装、杂货） | [来源1](https://www.dpworld.com/en/ports-terminals/uae/mina-rashid) |
| `facility_hamriya_dubai` | 哈姆里亚港（迪拜）（Mina Al Hamriya (Dubai)） | 沿海多用途商港（杂货、散货、滚装） | [来源1](https://www.dpworld.com/en/ports-terminals/uae/mina-al-hamriya) |
| `facility_hamriyah` | 哈姆里亚港（Hamriyah Port） | 多用途工业港（液化气、散货、杂货） | [来源1](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=286)、[来源2](https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf#page=287) |
| `facility_doha_old` | 多哈老港（Doha Port (Old Port)） | 邮轮客运港（游艇、旅游服务） | [来源1](https://visitqatar.com/intl-en/plan-your-trip/doha-port) |
| `facility_yanbu_north_crude` | 延布北原油码头（Yanbu North Crude Terminal） | 原油出口码头 | [来源1](https://www.aramco.com/-/media/downloads/working-with-us/ports-and-terminals-july-2025/10--yanbu-industrial-port-compressed.pdf) |
| `facility_yanbu_north_refined` | 延布北成品油码头（Yanbu North Refined Product Terminal） | 成品油出口码头 | [来源1](https://www.aramco.com/-/media/downloads/working-with-us/ports-and-terminals-july-2025/10--yanbu-industrial-port-compressed.pdf) |
| `facility_yanbu_south` | 延布南码头（Al Muajjiz）（Yanbu South Terminal） | 液体油品装卸码头 | [来源1](https://www.aramco.com/-/media/downloads/working-with-us/ports-and-terminals-july-2025/10--yanbu-industrial-port-compressed.pdf) |
| `port1117` | 鲁韦斯港（Al Ruwais） | 沿海商港（杂货、食品） | [来源1](https://web.archive.org/web/20250114055138/https://www.mwani.com.qa/English/Ports/Pages/AlRuwaisPort.aspx) |
| `port2031` | 阿卜杜拉国王港（King Abdullah Port） | 综合商港（集装箱、滚装、散货、杂货） | [来源1](https://www.kingabdullahport.com.sa/) |
| `port2218` | 舒盖格港（Shuqaiq） | 油品装卸港（油轮业务） | [来源1](https://www.iss-shipping.com/ports/al-shuqaiq/) |
| `port43` | 阿米拉巴德港（Amirabad Port） | 综合商港（粮食、石化产品、滚装、集装箱） | [来源1](https://web.archive.org/web/20211129032330/https://www.pmo.ir/en/portsandterminals/iranianports/amirabadport) |
| `port58` | 安扎利港（Bandar-e Anzali） | 综合商港（杂货、集装箱） | [来源1](https://web.archive.org/web/20220119034146/https://www.pmo.ir/en/portsandterminals/iranianports/anzaliport)、[来源2](https://web.archive.org/web/20211022040712/https://anzaliport.pmo.ir/en/home) |
| `port834` | 诺沙赫尔港（Nowshahr Port） | 商业货运港（货物装卸、仓储） | [来源1](https://web.archive.org/web/20211128054946/https://www.pmo.ir/en/portsandterminals/iranianports/noshahrport) |
| `fso151` | 阿曼海上石油终端1（源库名称）（Oman - Offshore Oil Terminal 1） | 海上油品终端（源目录未具名） | [来源1](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports_database/FeatureServer/0/query?where=portid+IN+%28%27fso151%27%2C%27fso158%27%29&outFields=%2A&returnGeometry=true&f=json) |
| `fso158` | 海上石油终端1（Saudi Arabia - Offshore Oil Terminal 1） | 海上油品终端（源目录未具名） | [来源1](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports_database/FeatureServer/0/query?where=portid+IN+%28%27fso151%27%2C%27fso158%27%29&outFields=%2A&returnGeometry=true&f=json) |
