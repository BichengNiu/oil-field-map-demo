"""Check local DuckDB coverage, source-file hashes, and append-key integrity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from monitor.common.paths import runtime_path
from monitor.storage.build_database import (
    ASSETS,
    _asset_rows,
    _catalog_rows,
    _local_documents,
    _port_rows,
)


REQUIRED_TABLES = {
    "database_info", "data_sources", "source_documents", "source_fetch_runs",
    "source_payloads", "oilgas_assets", "oilgas_asset_audits",
    "port_activity_audits", "port_catalog", "portwatch_catalog",
    "portwatch_daily", "portwatch_risk_capacity", "vessel_positions",
    "ais_reports", "sea_history_events",
}

DUPLICATE_GRAINS = {
    "data_sources": ("source_path",),
    "source_documents": ("source_path", "sha256"),
    "oilgas_asset_audits": ("review_date", "row_number"),
    "port_activity_audits": ("review_date", "row_number"),
    "port_catalog": ("source_name", "row_number"),
    "portwatch_catalog": ("node_kind", "portid"),
    "portwatch_daily": ("node_kind", "portid", "observed_date"),
    "portwatch_risk_capacity": ("portid",),
    "vessel_positions": ("source", "mmsi", "observation_key"),
    "ais_reports": ("source", "mmsi", "observed_at"),
    "sea_history_events": ("sea", "mmsi", "entered_at"),
    "source_payloads": ("run_id", "source_name", "partition_key"),
    "source_fetch_runs": ("run_id", "source_name"),
}


def _count(connection, table: str) -> int:
    return connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]


def inspect_database(database: Path) -> dict:
    report = {"database": str(database), "errors": [], "warnings": [], "coverage": {}}
    if not database.is_file():
        report["errors"].append("数据库文件不存在")
        return report

    documents = _local_documents()
    expected_documents = {
        (document["source_path"], document["sha256"]): document
        for document in documents
    }
    expected_sources = {
        (document["source_path"], document["sha256"])
        for document in documents
    }
    raw_snapshots = [
        document for document in documents
        if document["source_path"].startswith("snapshots/portwatch/")
    ]

    with duckdb.connect(str(database), read_only=True) as connection:
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
        missing_tables = sorted(REQUIRED_TABLES - tables)
        if missing_tables:
            report["errors"].append(f"缺少数据库表：{', '.join(missing_tables)}")
            report["coverage"]["tables"] = sorted(tables)
            return report

        report["coverage"]["tables"] = len(tables)
        stored_documents = set(connection.execute(
            "SELECT source_path, sha256 FROM source_documents"
        ).fetchall())
        missing_documents = sorted(expected_sources - stored_documents)
        report["coverage"]["local_structured_files"] = len(expected_documents)
        report["coverage"]["source_document_versions"] = _count(connection, "source_documents")
        report["coverage"]["missing_local_documents"] = len(missing_documents)
        if missing_documents:
            preview = ", ".join(path for path, _ in missing_documents[:8])
            report["errors"].append(
                f"source_documents 漏了 {len(missing_documents)} 个当前本地文件版本：{preview}"
            )

        source_rows = connection.execute(
            "SELECT source_path, sha256 FROM data_sources"
        ).fetchall()
        source_paths = [row[0] for row in source_rows]
        source_map = {path: digest for path, digest in source_rows}
        duplicate_source_paths = len(source_paths) - len(source_map)
        missing_source_metadata = sorted(
            path for path, _ in expected_sources if path not in source_map
        )
        stale_source_metadata = sorted(
            path for path, digest in expected_sources
            if source_map.get(path) != digest
        )
        report["coverage"]["data_source_paths"] = len(source_map)
        report["coverage"]["missing_data_source_paths"] = len(missing_source_metadata)
        if duplicate_source_paths:
            report["errors"].append(f"data_sources 有 {duplicate_source_paths} 个重复路径")
        if missing_source_metadata:
            report["errors"].append(
                f"data_sources 缺少 {len(missing_source_metadata)} 个本地结构化文件路径"
            )
        if stale_source_metadata:
            report["errors"].append(
                f"data_sources 文件散列未更新：{', '.join(stale_source_metadata[:8])}"
            )

        snapshot_keys = {
            ("port", str(record["portid"]), str(record["date"])[:10])
            for document in raw_snapshots
            for record in document["payload"]
            if isinstance(record, dict) and record.get("portid") and record.get("date")
        }
        stored_snapshot_keys = set(connection.execute(
            "SELECT node_kind, portid, cast(observed_date AS VARCHAR) FROM portwatch_daily"
        ).fetchall())
        missing_snapshot_keys = sorted(snapshot_keys - stored_snapshot_keys)
        report["coverage"]["portwatch_raw_snapshot_files"] = len(raw_snapshots)
        report["coverage"]["portwatch_snapshot_distinct_keys"] = len(snapshot_keys)
        report["coverage"]["portwatch_snapshot_keys_missing"] = len(missing_snapshot_keys)
        if missing_snapshot_keys:
            report["errors"].append(
                f"portwatch_daily 缺少 {len(missing_snapshot_keys)} 个本地快照节点/日期组合"
            )

        expected_typed = {
            "oilgas_assets": len(ASSETS),
            "oilgas_asset_audits": sum(1 for _ in _asset_rows()),
            "port_activity_audits": sum(1 for _ in _port_rows()),
            "port_catalog": sum(1 for _ in _catalog_rows()),
        }
        typed_counts = {table: _count(connection, table) for table in expected_typed}
        report["coverage"]["typed_tables"] = typed_counts
        for table, expected in expected_typed.items():
            if typed_counts[table] != expected:
                report["errors"].append(
                    f"{table} 行数为 {typed_counts[table]}，按当前本地源应为 {expected}"
                )

        table_counts = {
            table: _count(connection, table)
            for table in (
                "portwatch_catalog", "portwatch_daily", "portwatch_risk_capacity",
                "vessel_positions", "ais_reports", "sea_history_events",
                "source_payloads", "source_fetch_runs",
            )
        }
        report["coverage"]["dynamic_tables"] = table_counts
        report["coverage"]["portwatch_date_ranges"] = {
            row[0]: {"rows": row[1], "first": str(row[2]), "latest": str(row[3])}
            for row in connection.execute("""
                SELECT node_kind, count(*), min(observed_date), max(observed_date)
                FROM portwatch_daily GROUP BY node_kind ORDER BY node_kind
            """).fetchall()
        }

        for table, columns in DUPLICATE_GRAINS.items():
            grain = ", ".join(f'"{column}"' for column in columns)
            duplicate_count = connection.execute(
                f'SELECT count(*) FROM (SELECT {grain} FROM "{table}" '
                f'GROUP BY {grain} HAVING count(*) > 1)'
            ).fetchone()[0]
            if duplicate_count:
                report["errors"].append(
                    f"{table} 有 {duplicate_count} 组违反唯一键的重复记录"
                )

        wrong_metric_rows = connection.execute("""
            SELECT count(*) FROM portwatch_daily
            WHERE (node_kind = 'port' AND
                   (choke_total_vessels IS NOT NULL OR choke_capacity_dwt IS NOT NULL))
               OR (node_kind = 'chokepoint' AND
                   (calls IS NOT NULL OR import_tonnes IS NOT NULL OR export_tonnes IS NOT NULL))
        """).fetchone()[0]
        if wrong_metric_rows:
            report["errors"].append(
                f"portwatch_daily 有 {wrong_metric_rows} 行把港口与咽喉点指标写入错误字段"
            )

        current_runs = connection.execute("""
            SELECT source_name, status, record_count, started_at, error_message
            FROM source_fetch_runs
            QUALIFY row_number() OVER (
                PARTITION BY source_name ORDER BY started_at DESC, finished_at DESC
            ) = 1
            ORDER BY source_name
        """).fetchall()
        latest_runs = {
            row[0]: {"status": row[1], "records": row[2], "started_at": str(row[3]),
                     "error": row[4]}
            for row in current_runs
        }
        last_live_rows = connection.execute("""
            SELECT source_name, status, record_count, started_at, error_message, details
            FROM source_fetch_runs WHERE status <> 'skipped'
            QUALIFY row_number() OVER (
                PARTITION BY source_name ORDER BY started_at DESC, finished_at DESC
            ) = 1
            ORDER BY source_name
        """).fetchall()
        last_live_runs = {
            row[0]: {"status": row[1], "records": row[2], "started_at": str(row[3]),
                     "error": row[4], "details": row[5]}
            for row in last_live_rows
        }
        report["coverage"]["latest_source_runs"] = latest_runs
        report["coverage"]["last_non_skipped_source_runs"] = {
            source: {key: value for key, value in run.items() if key != "details"}
            for source, run in last_live_runs.items()
        }
        for source, run in last_live_runs.items():
            if run["status"] in {"partial", "error"}:
                report["warnings"].append(
                    f"最近一次非跳过来源运行 {source} 为 {run['status']}，详见 source_fetch_runs"
                )
            if source == "portwatch.daily.ports":
                details = run["details"]
                if isinstance(details, str):
                    try:
                        details = json.loads(details)
                    except json.JSONDecodeError:
                        details = {}
                if isinstance(details, dict):
                    coverage = details.get("coverage") or []
                    catalog_nodes = details.get("catalog_nodes")
                    if catalog_nodes and coverage:
                        nodes_with_rows = sum(
                            1 for node in coverage
                            if isinstance(node, dict) and node.get("records", 0) > 0
                        )
                        if nodes_with_rows < catalog_nodes:
                            report["warnings"].append(
                                "最近一次 PortWatch 港口抓取有日度记录的节点为 "
                                f"{nodes_with_rows}/{catalog_nodes}，详细缺口见 source_fetch_runs"
                            )

    report["status"] = "error" if report["errors"] else (
        "warning" if report["warnings"] else "ok"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path,
        default=runtime_path("oil-field-map.duckdb"),
        help="要检查的数据库文件",
    )
    args = parser.parse_args()
    report = inspect_database(args.database.expanduser().resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if report["errors"] else 0)


if __name__ == "__main__":
    main()
