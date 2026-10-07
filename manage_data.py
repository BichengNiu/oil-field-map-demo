"""Operator migration, inspection, safe SQL retrieval and single-file backups."""
import argparse
from pathlib import Path

import duckdb
import data_store


def main():
    parser = argparse.ArgumentParser(description="统一监测DuckDB维护")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    sub.add_parser("status")
    query = sub.add_parser("query")
    query.add_argument("sql")
    query.add_argument("--limit", type=int, default=100)
    backup = sub.add_parser("backup")
    backup.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.command == "migrate":
        print(data_store.encode(data_store.initialize()))
    elif args.command == "status":
        print(data_store.encode(data_store.status()))
    elif args.command == "backup":
        args.destination.parent.mkdir(parents=True, exist_ok=True)
        if args.destination.resolve() == data_store.database_path():
            raise ValueError("备份目标不能覆盖运行数据库")
        args.destination.write_bytes(data_store.backup_bytes())
        print(str(args.destination))
    elif args.command == "query":
        statements = duckdb.extract_statements(args.sql)
        if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
            raise ValueError("query只接受一条SELECT查询")
        with data_store.connect() as conn:
            result = conn.execute(args.sql)
            names = [col[0] for col in result.description]
            rows = result.fetchmany(max(1, min(args.limit, 10000)))
        print(data_store.encode([dict(zip(names, row)) for row in rows]))


if __name__ == "__main__":
    main()
