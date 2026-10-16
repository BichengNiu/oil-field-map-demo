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
