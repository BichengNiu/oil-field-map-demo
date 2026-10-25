# 2026-10-25 油气产量复核

页面现仅统计原油、天然气，多选且默认全选。复核后展示100条：原油84条、天然气16条；备注为真实产量56条、估算产量44条。相同资产分别披露油和气可有两行，行数不是唯一地质油田数。两种商品的数量和均值不混加。

## 本轮纠正

- **份额误记**：Abu Safah的195,814桶/日是巴林获分配份额，不是100%全田产量，已排除；Awali的38,378桶/日为2024年原油年均，保留。[巴林政府原始文件，印刷第60、62页](https://www.rns-pdf.londonstockexchange.com/rns/7260H_2-2025-5-7.pdf)
- **漏显**：Gharraf2025年约180千桶/日与2022年补充记录不再因口径文字不同被误判为空间交叉，恢复明确全田范围的2025年披露，不相加。[所引运营方报道](https://www.iraq-businessnews.com/2025/07/08/dqoc-boosts-production-with-integrated-development-plan/)
- **估算门槛**：11条缺可靠量测的2015年战时文献估计、6条依据时点不明估计、1条匿名消息估计仅归档，不进入统计。两田回退到EIA明确标注2011年的历史估计。[原论文](https://www.mdpi.com/2076-0760/5/2/20)、[EIA叙利亚原报告](https://www.eia.gov/international/content/analysis/countries_long/Syria/archive/pdf/syria_2013.pdf)
- **统计范围**：东巴格达南区、伊朗侧部分范围在名称中明确，不冒充全田；North Arabia按开发项目展示。
- **数值和来源**：修正“.7”小数解析；报告下限不误标为自行估算，也不当作精确点值。Genel来源更换为数值一致的可检索官方报告。[替代官方报告](https://genelenergy.com/wp-content/uploads/2020/09/Genel-Trading-and-operations-update-FINAL-PR.pdf)

## 数值与估算复算

20条年度量换算核对年产量、365/366天分母、单位与舍入。Hawler使用100%毛合计，不将65%工作权益量当作全田量。[EITI2021表57–58](https://eiti.org/sites/default/files/2024-01/Iraq%202021%20EITI%20Report.pdf)、[EITI2016](https://eiti.org/sites/default/files/attachments/iraq_2016_eiti_report.pdf)、[Forza AIF2022](https://www.forzapetroleum.com/data/financial/2022_AIF_-final-.pdf)

Gabar按23.1百万桶×60%÷181天得到约76.6千桶/日；Sakarya按1641百万立方米×92%÷181天得到约8.34百万立方米/日。政府总量与份额有舍入，天然气总量还使用“超过1641”的基准，均只作为有依据的近似估算，不能标为独立实测。[土耳其能源部原文](https://enerji.gov.tr/haber-detay?id=31903)

IEEJ的9个油田值对应2010年估计列，未采用2017年预测列。QatarEnergy的15个油/气值核对2024年、单位和田名对应；ShaMaran使用100%毛产量列，不取公司净量。[IEEJ第4–5页](https://eneken.ieej.or.jp/data/4534.pdf)、[QatarEnergy第12页](https://www.qatarenergy.qa/en/MediaCenter/Publications/QatarEnergy_Investors_Presentation_November_2025.pdf)、[ShaMaranQ2原文](https://shamaranpetroleum.com/news/shamaran-reports-second-quarter-2026-results-122891/)

区间按要求取中点并标估算；6条只有上下限的记录不虚构点值，不按零参与平均。天然气只按1立方英尺=0.028316846592立方米换单位，参考状态沿用来源，不做温压、热值或油当量换算。

## 验证及界限

46项测试和56种国家/商品筛选组合检查通过；已登记范围内，同一商品的选用单元未发现重叠。完整记录保留了公式、来源访问状态、逐行选用/排除原因及当前表格：[审查JSON](production_quality_recheck_2026-10-25.json)。

57个原始链接中53个本轮获得可读正文，3个返回403，1个为短响应。ADNOC两项及Genel通过官方缓存/替代报告补证；LeMonde只核对搜索摘要，未读全文。正文可访问或数字匹配不等于独立验证生产计量仪器；非核心来源结合了既有逐项审计记录。

表内仍有历史数值和4条依据年份未明确记录，不能把整张表当作当前实时产量。未穷尽的地质、合同交叉关系仍需补核；线上页面因当前无可用浏览器尚未实机验证。
