"""Authorized historical entry reports, independent of PortWatch download status."""
import hmac
import streamlit as st

import report_data
import sea_history
import data_store


def render_sea_history_panel():
    st.subheader("海域历史数据")
    state = data_store.status()
    st.caption(f"统一DuckDB：AIS观测 {state['counts']['ais_reports']:,} 条；进入事件 {state['counts']['sea_entries']:,} 条。")
    config = report_data.sea_history_config()
    try:
        result = report_data.card_sea_history()
        if result.get("error"):
            st.warning(result["error"])
        if result["rows"]:
            days = [row["date"] for row in result["rows"]]
            st.write(f"已接入 {result['source']}；历史范围 {min(days)} 至 {max(days)}。")
            if result.get("started_at"):
                st.caption(f"持续观测始于 {result['started_at']}。首次出现作基线，不计进入；已记录艘次不代表全部实际船流。"
                           "观测窗口不完整时不计算环比、同比。")
            else:
                st.caption("各海域完整日期覆盖见下表；当前月累计采用四海域共同的最新完整日。")
            st.dataframe(result["rows"], hide_index=True, width="stretch", height=200)
        else:
            st.info("尚未导入完整海域历史事件。实时船位不能用于通过艘次、环比和同比。")
    except Exception as exc:
        st.error(f"海域历史档案读取失败：{exc}")
    if st.button("刷新海域历史数据", key="sea_history_sync"):
        try:
            with st.spinner("正在读取已配置的海域历史交付源…"):
                synced = sea_history.sync_source(config)
            st.session_state["sea_history_sync_error"] = None
            st.session_state["sea_history_sync_message"] = (
                "海域历史数据已更新。" if synced else "未配置远端交付源；已显示本地档案。")
        except Exception as exc:
            st.session_state["sea_history_sync_error"] = f"海域历史更新失败：{exc}"
            st.session_state["sea_history_sync_message"] = None
        report_data.card_sea_history.clear()
        st.session_state.pop("sea_history_import_result", None)
        st.rerun()
    if message := st.session_state.get("sea_history_sync_message"):
        st.success(message)
        st.session_state.pop("sea_history_sync_message", None)
    if error := st.session_state.get("sea_history_sync_error"):
        st.warning(error)
    with st.expander("接入历史进出事件"):
        st.markdown(
            "需要波斯湾、红海、阿曼湾、亚丁湾的**自定义海域进入事件**，"
            "同船再次进入另计。可向[VesselFinder历史数据服务]"
            "(https://www.vesselfinder.com/historical-ais-data)申请四海域事件报告；"
            "实际覆盖须由供应商确认。港口挂靠、海峡通过、AIS位置和去重船只数不能直接导入。"
        )
        st.caption("ZIP包含manifest.json、events.csv及供应商确认完整日的coverage.csv。"
                   "需要固定海域边界，并包含上周、前周、本月、上月同期和去年同期。"
                   "字段转换与服务器交付源配置见项目SEA_HISTORY_INTEGRATION.md。")
        st.download_button("下载历史导入模板", sea_history.template_bundle(),
                           file_name="sea_history_template.zip", mime="application/zip")
        import_token = config.get("SEA_HISTORY_IMPORT_TOKEN")
        if not import_token:
            st.caption("服务器可配置历史交付文件或交付地址自动接入；启用网页导入需先配置管理员导入口令。")
            return
        supplied_token = st.text_input("管理员导入口令", type="password", key="sea_history_import_token")
        allowed = bool(supplied_token) and hmac.compare_digest(supplied_token.encode(), import_token.encode())
        if allowed:
            st.download_button("备份统一DuckDB", data_store.backup_bytes, file_name="monitoring.duckdb",
                               mime="application/octet-stream", key="monitoring_db_backup")
        uploaded = st.file_uploader("历史海域事件ZIP", type=["zip"], key="sea_history_upload", disabled=not allowed)
        if st.button("导入历史数据", disabled=uploaded is None or not allowed, key="sea_history_import"):
            try:
                imported = sea_history.import_bundle(uploaded.getvalue(), sea_history.archive_path(config))
                report_data.card_sea_history.clear()
                report_data.cached_print_report.clear()
                st.session_state["sea_history_import_result"] = imported
                st.rerun()
            except Exception as exc:
                st.error(f"未导入：{exc}")
        if imported := st.session_state.get("sea_history_import_result"):
            st.success(f"已导入 {imported['events']:,} 条进入事件、{imported['days']:,} 个海域完整日；地图和报告共用此档案。")
