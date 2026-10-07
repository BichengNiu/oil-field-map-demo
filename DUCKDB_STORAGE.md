# 统一数据存储与可选采集

## 本次整理的结果

审计发现 38 个 JSON/CSV 数据文件、AIS/港口缓存/海域事件三个独立 SQLite 入口，以及内存中的展示缓存。主要问题是数据入口分散、时间与粒度不同，不能把历史审计、最新观测、油田产能和实际产量直接混算。统一为一个数据库解决存储和访问一致性；不会凭空补齐缺失的历史或实际产量。

现有 38 份来源材料与本次四海域边界共 39 份文件入库；原始文件按 SHA256 保留完整字节，另有 12,811 条可用 SQL 检索的来源记录。现有 Python 目录规则生成油气目录后保存并从库内读取，Decimal 数值、来源期、单位和产能/实产区别保留。运行中的港口日表、查询缓存、原始查询响应、AIS 报告、海域事件及采集状态统一读写 **`monitoring.duckdb`**。

Git 中的原始 JSON/CSV 是版本化的启动种子及迁移备份，不继续承担独立运行档案职责；页面内存缓存只用于加速。代码、CSS、地图脚本和可再生成的下载/报告文件不作为业务事实入库。DuckDB 正常运行还会生成锁文件及短暂 WAL，它们不是独立业务数据源。

## 表与检索

| 表/视图 | 粒度与用途 |
| --- | --- |
| documents | 每份来源文件一行，原始字节、SHA256、类型、入库时间 |
| document_rows | 来源路径、JSON 章节、行号唯一，保留 CSV/JSON 的原始记录 |
| catalogs / asset_catalog | 油气/港口/通道目录；资产按国家及名称唯一，目录与观测不混合 |
| portwatch_daily / portwatch_metrics | 来源类型、节点、UTC 自然日唯一；真实零与空值区分 |
| portwatch_cache / source_queries | 已校验查询缓存、去重的源站原始响应及查询条件 |
| ais_reports / ais_positions | MMSI、真实观测时间、来源唯一；源时间与接收时间分开 |
| sea_entries / sea_daily_observed | 来源、固定边界版本、海域、MMSI、进入时间唯一；同船多次进入另计 |
| sea_vessel_checkpoints | 每船每 UTC 日保留最新识别状态；迟到报告触发有界复算 |
| sea_coverage / sea_manifests | 授权历史交付的供应商完整性声明及边界版本 |
| collection_runs | 每次轮询的开始、结束、成功/部分/失败、条数与错误 |
| archive_imports / app_meta | 导入证据、迁移标记、采集起点等运行元数据；不存密钥 |

本地运行：

```bash
python manage_data.py migrate
python manage_data.py status
python manage_data.py query 'SELECT kind,COUNT(*) AS records FROM catalogs GROUP BY kind'
python manage_data.py query 'SELECT sea,day,SUM(passages) AS passages FROM sea_daily_observed GROUP BY sea,day ORDER BY day DESC'
python manage_data.py query "SELECT country,name,metric_type,measurement_date,value_numeric,unit FROM asset_catalog WHERE value_numeric IS NOT NULL"
python manage_data.py backup /backup/monitoring.duckdb
```

也可用 DuckDB 客户端/数据库工具直接检索导出的数据库。应用与采集服务的访问采用线程锁、跨进程文件锁、短事务，连接关闭后释放数据库锁；外部工具请查询备份，或遵循相同文件锁协议，避免持有运行数据库的长连接。部署为单机共享磁盘，不能把同一文件复制到多台服务器后仍视为一个数据库。

## 从今天起如何计数

采集起点以服务第一次启动时的真实时间保存；2026-10-06 的本地验证采集起点为 11:55:59 UTC（19:55:59 上海时间），不能声称覆盖了当天此前时段。部署环境也会保存其真实启动时间，旧 AIS 档案自动迁移，不把旧样本回填为完整覆盖。

Streamlit 页面仅在手动刷新时发起一次 Open Waters 四组查询，均不超过 100 平方度免费查询上限；增加亚丁湾及四海域边界两侧约 0.3° 的观测带。页面不会自动连接 AISStream，也不会定时读取港口目录。独立采集服务仍可按下方命令显式启用周期轮询和 AISStream 订阅；原始消息的 API Key 不入库、不发给浏览器。源站日期与本机采集时间分开，限流采用退避重试。

进入事件使用 Marine Regions/IHO 四个固定多边形，不能用查询矩形或 MMSI 月去重代替。一条船首次出现只建立基线。海域内侧及外侧各约 0.01° 的缓冲区用于抑制边界抖动，连续两次稳定位置确认状态改变；外→内产生一艘次，内→外只更新状态，离开后再进入可再产生一艘次。观测间隔超过 30 分钟、推算航速超过 60 节时重新建立基线，不据此推断进出；同船同观测时间的多源位置显著冲突时该时间点不用于推断。同一事件跨页刷新、重复采集、进程重启不增计。

事件是**已确认的 AIS 观测进入次数**，不是四海域全部真实船舶的普查。免费接收站无报文不能证明当地没有船只；位置消失不能证明已经离开。边界版本、识别方法、进入前观测时间、确认时间及来源均可追溯。底图和实时船舶表可包含边界观测带的位置，统计海域仍以固定多边形为准。

地图及报告的“本月已记录通过”显示本月从采集起点开始的已记录艘次，使开始积累的第一个月也能看到真实进度。首日仅部分时段；上周、环比和同比只有相应自然周/同期观测过程连续且没有失败/截断时才计算，否则显示“—”。月份比较采用同样的日数及上海时区时刻；初始月不完整，不能据此生成完整月的基期。观测过程连续只说明程序的采样连续，不代表上游接收站全海域覆盖。

未来授权事件文件可导入同一个 DuckDB；选中的供应商历史与本地观测分别保留，卡片采用一种来源口径，不把不同边界或供应商的事件直接相加。

## 迁移、持久性与后台服务

应用启动会把旧 `AIS_ARCHIVE_PATH`、`PORTWATCH_DOWNLOAD_CACHE`、`SEA_HISTORY_ARCHIVE_PATH` 的 SQLite 数据只读迁入新库，成功后记录迁移标记，重复启动不重复导入；原库保留作回退备份。三个旧变量只选择迁移来源，**运行数据路径统一用 `MONITORING_DB_PATH`**。

```toml
MONITORING_DB_PATH = "/persistent-data/monitoring.duckdb"
```

默认项目下 `runtime/monitoring.duckdb` 适合开发；正式部署应指向持久磁盘并定时备份。无持久盘的云容器重建会丢失新增数据，Git 内的种子只能恢复原始材料，不能恢复之后的 AIS 观测。“数据下载”页的管理员导入口令通过验证后可下载统一数据库备份；凭据只放服务端 Secrets 或环境变量。

Streamlit 页面启动时不启后台采集，浏览器刷新也不会自动拉取外部数据；每次点击船位刷新会单次查询并归档。需要连续采样时，才显式启动独立采集服务；**托管平台休眠、停机或容器终止会中断采集**。已提供独立采集入口及 `deploy/monitoring-collector.service`；服务环境与 APP 配置相同的持久数据库路径，在同一主机使用文件锁协作。手动刷新部署不要同时运行该服务。

```bash
python collector.py --with-portwatch --poll-seconds 60
python collector.py --once --with-portwatch
```

systemd 示例的项目、Python 和环境文件路径需与实际服务器一致；服务重启恢复数据库内检查点，不从零累计。首次上线只建立观测基线，短时间“0 个已记录进入事件”并不是海域没有船舶。

本轮实际核对：39 个文件的原始字节/哈希；来源行主键；资产数量、精确数值类型、来源日期和单位；旧三库迁移及重复迁移；事务回滚、并发访问、迟到位置纠正及检查点恢复。具体执行证据保存在测试、来源表与 `collection_runs`；不把检查日期当成数据日期。
