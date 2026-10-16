# 11 国港口与输油管线再次核查

**结论：不能宣称当前 170 条港口目录已完整、准确且无遗漏。** 已覆盖现用 PortWatch 全国家查询的 91 个节点，并闭合固定 WPI 镜像的 125 个条目；扩大到官方设施名录和 UN/LOCODE 后仍发现遗漏、混合粒度及明确未决项目。

## 港口数据与质量

- 170 条、11 国；9 个必需字段无空值，港口 ID、规范化英文名和 WPI 编号无重复。双语字段和来源字段完整不等于正式名称及精确泊位已全部认证。
- 91 个节点具独立日度统计，2019-01-01—2026-10-09 共 258,349 条；79 个只有目录。表和图不能解释成覆盖所有港口的全国总量。
- 两条类型未决：`wpi48035` 气体船码头未分 LNG/LPG；`wpi48533` 液体货种未定。
- 四条来源身份例外：`wpi48406` 英文 LNG 与 LPG 业务冲突；`wpi48268` Mubarraz/Mubarek 差异；`fso151`/`fso158` 为未具名海上终端。
- 3 km 内有 10 对点位，需要区分父港、子终端和坐标代表点；Free Port/Zayed 共用一点也不能直接推定同一设施或精确定位。没有凭距离删除或合并日度事实。

## 逐国复核

| 国家 | 当前目录 | 本次结论与依据 |
|---|---:|---|
| 阿联酋 | 34 | 富查伊拉港务局单列迪巴港（Dibba Port），当前34条没有该港；RAK Maritime City 官方归于 Saqr Port/Free Zone，作为园区/港区关系处理，不凭名称多建统计节点。 [来源1](https://fujairahport.ae/port-overview/dibba-port/) [来源2](https://www.rakports.ae/ports/saqr-port-and-free-zone/) |
| 沙特阿拉伯 | 25 | 主要商业和工业港已有目录；法拉桑客运港（Farasan ferry terminal）未单列，TGA 经 SPA 公布了吉赞—法拉桑渡轮客运及车辆数据。Jubail 商业/工业港与现有复合节点仍需核统计边界。 [来源1](https://www.spa.gov.sa/en/N2163485) [来源2](https://www.iaphworldports.org/memberports/saudi-ports-authority/) |
| 伊朗 | 23 | PMO 的 IAPH 成员目录列有 Bandar Lengeh（页面拼作 Lengel），当前23条无独立对应。Neka 在 UN/LOCODE 与政府调研资料出现；与 Amirabad 的设施边界须再核，不直接视作重复或借用其统计。 [来源1](https://www.iaphworldports.org/iaph-md/directory/port_details/61) [来源2](https://openjicareport.jica.go.jp/pdf/11868726_02.pdf) |
| 阿曼 | 10 | 七处主要 Asyad 商港已有对应，但 Mwasalat 官方渡轮线路列出的阿曼迪巴（Dibba）、利马（Lima）、沙纳（Shannah）、马西拉（Masirah）均未单列。阿曼 Dibba 与阿联酋 Dibba 属于不同国家，不能跨国消歧。 [来源1](https://mwasalat.om/) [来源2](https://nfc.mwasalat.om/FAQs) |
| 埃及 | 36 | 主要港口及此前缺失节点已补录；交通部门仍单列塔巴海港/塔巴高地客运码头，当前36条无 Taba 对应。El Max 为整合 Alexandria/Dekheila 的开发项目，不等于另一套独立日度事实。东西塞得港共用现有节点的边界仍待细核。 [来源1](https://www.mts.gov.eg/en/port/مارينـا-طابا-هايتس-السياحية/) [来源2](https://sis.gov.eg/en/egyptians-abroad-portal/mega-projects) |
| 卡塔尔 | 8 | Mwani 的 Hamad、Old Doha、Al Ruwais 三港已对应，工业港已列。QatarEnergy 法规列有 Ras Abu Aboud；目前没有独立目录对应，尚需核对支持基地与 Doha 的范围及现时用途。QAPCO/Qchem 等为工业终端候选，不能当成 Mesaieed 之外的独立港口直接加总。 [来源1](https://www.mwani.com.qa/English/AboutUs/Pages/default.aspx) [来源2](https://www.qatarenergy.qa/en/whoweare/governance/Pages/LegalRegulatoryFramework.aspx) |
| 伊拉克 | 8 | Umm Qasr、Khor Al Zubair、Al Maqal/Al Basrah、Abu Flous 及 Faw 项目已有条目；Umm Qasr 南北港未拆成两套统计。UN/LOCODE 的 Baghdad 等地点不因含港口功能代码就等同于独立海港。没有获得所有私有码头的完备清单。 [来源1](https://www.aspf.org.eg/ardirectory/default/viewArticle/53-ميناء-أبو-فلوس/21) [来源2](https://en.alfawport.gov.iq/) |
| 科威特 | 6 | KPA 官方三处主要商业港 Shuwaikh、Shuaiba、Doha 已对应，另列三处油品港。Mubarak Al Kabeer 的开发阶段及小型渔港/游艇设施不在这份商港清单证明范围内，不能据此宣布全部设施齐全。 [来源1](https://kpa.gov.kw/en/about-us/) |
| 巴林 | 5 | 主要商港及油气设施已有目录，但官方还有私有码头许可体系；Alba/GPIC 等共用工业码头与 Sitrah 的父子关系、ASRY 修船泊位及客运码头未逐设施建模，不能宣布五条记录覆盖全部。 [来源1](https://www.mtt.gov.bh/index.php/private-jetties) [来源2](https://www.albasmelter.com/uploads/Stakeholder_Engagement_Plan_of_Port_Capacity_Upgrade_Project.pdf) [来源3](https://www.asry.net/FacilitiesInfrastructure/Facilities/) |
| 也门 | 11 | YASPC 的 Mukalla、Nishtun、Socotra 三港均已有对应，原 WPI 比对缺口已闭合；Little Aden 等港区/终端与 Aden 的覆盖边界尚未细化，其他沿岸小港须继续消歧，不能从 WPI 齐全推导全部海岸设施齐全。 [来源1](https://www.yaspc.co/en) |
| 吉布提 | 4 | Djibouti、Doraleh、Tadjourah、Ghoubet 已列；DPFZA 的 Damerjog Liquid Bulk Port 为具名液体散货港项目，当前四条没有对应。应补项目目录，不能从没有现时船舶统计推定不存在。 [来源1](https://www.dpfza.gov.dj/damerjog-liquid-bulk-port-modern-oil-terminal-world-class-capacity) [来源2](https://www.dpfza.gov.dj/index.php/visit-ethiopian-investment-holdings-damerjog-industrial-and-port-facilities) |

## 尚未收录的具名设施/项目

这些是目录缺口，不等同于新增可用日度统计；本次核查未把它们悄悄当作已经入库。

- 阿联酋：迪巴港（Dibba Port）。
- 沙特阿拉伯：法拉桑客运港（Farasan ferry terminal）。
- 伊朗：伦格港（Bandar Lengeh）。
- 阿曼：迪巴渡轮港（Dibba ferry terminal）。
- 阿曼：利马渡轮港（Lima ferry terminal）。
- 阿曼：沙纳渡轮港（Shannah ferry terminal）。
- 阿曼：马西拉渡轮港（Masirah ferry terminal）。
- 埃及：塔巴海港/高地客运码头（Taba port / Taba Heights marina）。
- 吉布提：达梅尔乔格液体散货港（Damerjog Liquid Bulk Port）。

## UN/LOCODE 交叉核对

官方生产版 2025-1 中，这 11 国有 255 条港口功能地点；当前预发布版有 262 条。以 WPI 编号桥接或规范化英文精确匹配可对应生产版 103 条，剩余 152 条是待消歧地点，**不是 152 个已证实漏港**。许多条目是别名、港区、工业基地或内陆城市；预发布新增 7 条也含 Al Ain 等内陆地点，不能直接导入成海港。完整逐条清单、版本包 URL 与 SHA256 已保存于机器审计。

## 输油管线核查

- 重新获取相同固定 GEM 几何源，SHA256 与原证据一致；全球 1,556 项中有 1,317 条 Oil 记录，涉及当前 11 国的 243 条分段均在项目的 250 条区域目录内，漏导入 ID 为 0。跨境及此前其他国家记录保留，不按本次港口范围删除历史。
- 这只证明相对该地图源导入完整，不能证明各国实际管网完整；吉布提在该源为 0 也不是没有油品管道的证明。
- 阿联酋第二条东西线（ADNOC West-East Pipeline）确为遗漏项目：ADNOC 2026-05-15 确认在建、预计 2027 投产，目标为经富查伊拉出口能力翻倍。项目补入 `data/pipeline_projects.json`，可搜索/查看资料；官方未给独立运力数值及可核验几何，保持空值和无路线，不套用旧 ADCOP 的 1.8 百万桶/日或其坐标。
- 既有源备忘明确缺几何的伊拉克 Khor Al-Amaya 终端线、伊朗 Goreh B–Genaveh 馈线、沙特 East–West 扩容条目继续保留为待补证据；扩容不等于可凭空新增平行线。
- 端点冲突的 P0640（油）及 P5684（气）继续保留证据、暂停绘制。低精度路线的精度在弹窗中保留，不再用第三种线型表达精度。

## 页面变更及验证口径

港口筛选顺序为：时间范围、聚合方式、国家、水域、港口类型、港口。名称查找使用稳定 ID，选择后开启相应图层并定位；弹窗固定于图例下方。只有一种实线和一种虚线：运行中实线，其他状态虚线，弹窗保留具体建设/规划/闲置/退役状态，避免把退役误写成未投产。三个来源数据日无 UTC 后缀，在左下角逐行显示。

浏览器测试覆盖油气、港口、船舶、输油、输气及无几何项目，验证连续切换、平移后固定位置和无 JavaScript 异常；无几何项目只打开资料，不制造地图定位。

[机器审计](audits/port_and_pipeline_recheck_2026-10-16.json)；[可复算 notebook](audits/port_and_pipeline_recheck_2026-10-16.ipynb)。部分官方站点直连超时/403/503，已保存失败状态并使用官方页面的可访问索引交叉核实，不把拒绝页当成有效完整名录。

## 2026-10-17 缺口处理结果（后续更新）

上文是 170 条目录时的核查基线。此前列出的九处设施现已全部补入，当前展示 **179 条、11 国**，归档保留厄立特里亚条目共180条。阿曼迪巴与阿联酋迪巴分别建 ID；塔巴海港与塔巴高地码头按政府名称/边界记录为一处，未重复新增。

四处使用官方资料的代表点：阿联酋迪巴、伊朗伦格、阿曼马西拉（希尔夫）、埃及塔巴。迪巴、伦格及希尔夫使用 NGA 航路指南的港口所在地代表点；塔巴使用埃及海运部门公布的五个边界点平均值，仅作代表点。另通过具名渡轮设施及运营商航线端点核对 OpenStreetMap，补齐法拉桑、阿曼迪巴、利马、沙纳四处代表点（ODbL 1.0；节点版本及端点关系见审计），共八处可绘制。达梅尔乔格仍保留空坐标：附近通用名油码头多边形尚无唯一设施身份关系，不能仅按邻近归属。该港在筛选列表及地图搜索中可以查看资料，搜索不跳到虚构位置。官网文字、同名村镇、海岬、摄影坐标都不当作实测泊位点；尤其不得把阿联酋迪巴点用于阿曼迪巴。

九处都没有独立 PortWatch 进港统计：91个独立日度节点保持不变，不将它们计为9套新增流量；缺失不填零。港口类型继续采用原有九大类，业务特点保留具体渡轮、干散货或多货种信息。

两项精确货种仍未有可靠主键对应证据。NGA 只证明 `wpi48035` 为气体船码头；IFC证实 Sokhna 存在氨装卸设施，但无法据同城名称把该设施绑定给这个 WPI ID。`wpi48533` 的凝析油线索也尚无可核验现时运营商资料闭合，继续保留货种待核，不假定为 LNG、LPG 或原油。这是未解决事项，不计为核实完成。

伊拉克豪尔阿迈耶终端输油管线及伊朗古雷B—格纳韦馈线已补入无几何项目资料，可搜索；伊拉克政府合作资料仅证明历史设施，伊朗较新目录的规划/在建状态存在冲突，两者当前状态保持待核，不伪造路线。端点冲突的 P0640/P5684 仍隔离。

沙特东西原油系统 P0551 改用 Aramco 2026-05-10 一季度公告披露的最大运力 **7 百万桶/日**；旧 EIA 5 百万桶/日基准保存在历史证据内。运力不等于实时流量；扩容更新现有系统，不凭空另画两根可重复加总的线路。

本轮源证据、逐条新增记录、坐标推导和未决原因见 [后续审计](audits/coverage_gap_followup_2026-10-17.json)。UN/LOCODE余下地点、私有码头及父子港区仍需消歧，不能宣称实际各国港口与管网已全部穷尽。

## 2026-10-17 再查及地图入口修正（最新结果）

- 按最新要求，所有**没有可靠路线坐标的管线项目**从图例、地图搜索和资料弹窗入口移除；不再把项目名称当作图例项。阿联酋第二条东西线、豪尔阿迈耶终端线、古雷B—格纳韦馈线的原始证据继续归档，暂不出现在地图界面。原有可绘制路线、类型图例及坐标冲突隔离保持有效。
- 达梅尔乔格坐标取得新证据：UKHO 2025年第45期、第50期航海通告明确将前导标 FA1（D7282.1）归于 Port pétrolier de Damerjog，坐标11°30.92′N、43°15.08′E。2026年第12期还列出同名进港航道浮标。采用该**港口前导标参考点**定位，明确不是装卸泊位中心，也未把附近无名油码头多边形直接认领。此前补录九处现在均有来源代表点；目录仍179条，统计节点仍91个。
- 塔赫里海上码头（WPI48533）取得新的专业技术来源：SGS《Crude Oil Terminal & Custody Transfer Data》2010–2011版将Bandar Taheri/NIGC（IRBTN、VCF6A）列入油品终端交接计量资料；与NGA的同名WPI/NIGC对应关系结合，可以核实为**油品港及终端**大类。业务为海上油品装卸/单点系泊；不据历史技术册确认当前运行情况或精确凝析油品种。原疑点与旧判定保留于审计历史。
- 苏赫纳气体船码头（WPI48035）仍只获气体船设施证明；LNG、LPG及氨设施各自的名称/位置资料未能与该编号唯一对应，继续保留类型待核。三项未绘制项目仍无可靠连续路线；P0640/P5684端点冲突也未获新证据解决。

详细文件、下载散列、版本、页码及未决项见 [本轮再查记录](audits/map_gap_research_2026-10-17.json)。以上更新取代上文有关“达梅尔乔格无坐标”“两项类型待核”及“无几何项目可搜索”的旧状态，旧段落保留审计时间顺序。


2026-10-17 深入追查：苏赫纳WPI48035已用DFC托管的2015年环评（图5-2旧海图、图4-53 EHC港区）与IFC 35033披露关联为既有丙烯气体船码头，类型改为“化工气体港”，不归入LNG/LPG。液氨改扩建为历史计划，不据此认定当前已投用。保留原ID、坐标和完整旧审计。现有179条目录均有已审核大类，但这不等于穷尽所有港口、货种或当前状态。

阿联酋新West-East设计承包商资料确认500公里、48英寸、Jebel Dhanna至Fujairah MOT，未提供连续坐标和独立运力。KAAOT不是整座终端没有路线：GEM P5290已有标注KAAOT终点的ICOEEP路线，缺口应限定为历史旧线与扩建线的逐线对应。Bechtel工程作者的1995年文章确认Umm Shaif—Das实际选线绕行，旧路线图现返回410；不能用端点直连修复错误GEM线。Goreh B—Genaveh新馈线仍缺独立路线与一致的最新阶段证据；旧P5376不作为替代。上述四类路线问题尚未全部解决，详见audits/deep_gap_research_2026-10-17.json。
