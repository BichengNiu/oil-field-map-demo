# 港口经营状态：规则和官方信息入口

核查日期：2026-10-16。当前 PortWatch 港口日记录截至2026-10-09。

此前132个港口的人工目录状态为：129个待核、2个仅确认带时点的装船活动、1个商业启用待核；状态函数没有使用进港事实，因此界面大量显示未知。现在按用户要求，将最近7个日历日记录完整且每天进港艘次均大于0作为“正常”的活动证据。当前数据下16个港口满足该规则，116个仍为未知。零进港和缺报均不能证明停运。正常表示该统计范围持续有进港活动，不表示所有泊位、货种或航线均不受限制。

明确且适用于所显示日期的运营/关闭公告优先；晚于数据日期的公告不能回填到历史日期。当前没有新增经核实的停运公告，不将网站可访问或企业简介当成实时正常证据。推导标签在展示端只读计算，原始人工字段与日事实保留。

| 官方渠道 | 本轮结果与适合查证的信息 |
|---|---|
| [DP World 杰贝阿里港](https://www.dpworld.com/en/ports-terminals/uae/jebel-ali-port)、[新闻](https://www.dpworld.com/en/news) | HTTP 200；可确认运营主体、港口服务与官方更新；企业介绍和新闻首页本身不能证明全部港口今日正常。猜测的 `/en/uae/notices` 路径为404，未作为有效通告源。 |
| [AD Ports 新闻公告](https://www.adports.ae/media-center/news/press-releases/) | HTTP 200；页面列有2026-03-04业务连续性公告。公告有日期，不能把3月声明直接作为10月当前状态。停复运应查具体港口、码头、货种、生效和解除时间。 |
| [SOHAR 官方新闻](https://soharportandfreezone.om/news-insights/) | HTTP 200；可追查港口运营、海事与客户公告，需逐条判断适用范围。 |
| [APM Terminals Bahrain](https://www.apmterminals.com/en/bahrain)、[船期入口](https://www.apmterminals.com/track-and-trace/vessel-schedule?terminal=BHKBS) | HTTP 200；首页有船期及 operational updates 入口。船期页为动态应用，静态HTTP 200不代表已获取实际船期。 |
| [APM 2026-10-14客户通知](https://www.apmterminals.com/en/bahrain/investors/investor-news/2026/261014-Truck-Registration-Requirements-and-RFID-Compliance) | HTTP 200；明确标为 Operational update / Customer Advisory，内容为卡车登记和RFID要求。这是可用的运营信息渠道，但不能当作“全港所有设施正常”的公告，也不能用于10月9日历史状态。 |
| 沙特 Mawani、Asyad、卡塔尔 Mwani | 本轮公开页面分别遇到405、503或访问失败，未将失败解释成港口停运。已有港口目录链接保留，需使用可核验的正式公告、海事通告或运营方交付。 |

本轮来源URL、重定向、HTTP状态和页面SHA256存于[来源核查记录](audits/port_operations_sources_2026-10-16.json)。尚未把这些异构网页自动转成132港的统一实时停复运接口，也没有建立其他采集任务。后续如接入公告，应由现有采集发布脚本归档逐港证据，展示端继续只读，不直接抓网站。
