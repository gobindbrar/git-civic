"""Idempotently copy civic.db data into the Replit development PostgreSQL database."""

import argparse
import os
import sqlite3
from pathlib import Path

import psycopg
from psycopg import sql

BASE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        choices=["development"],
        required=True,
        help="The importer intentionally cannot target production.",
    )
    parser.add_argument("--source", type=Path, default=BASE / "civic.db")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required for the development import.")
    if not args.source.is_file():
        raise SystemExit(f"SQLite archive not found: {args.source}")

    source = sqlite3.connect(f"file:{args.source}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        with psycopg.connect(database_url, connect_timeout=8) as destination:
            for table in ("events", "rsvps", "check_ins"):
                exists = source.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
                if not exists:
                    continue
                source_columns = [row["name"] for row in source.execute(f"PRAGMA table_info({table})")]
                with destination.cursor() as cursor:
                    cursor.execute(sql.SQL("SELECT * FROM {} LIMIT 0").format(sql.Identifier(table)))
                    target_columns = [column.name for column in cursor.description]
                columns = [column for column in source_columns if column in target_columns]
                if not columns:
                    continue
                query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
                    sql.Identifier(table),
                    sql.SQL(", ").join(map(sql.Identifier, columns)),
                    sql.SQL(", ").join(sql.Placeholder() for _ in columns),
                )
                copied = 0
                with destination.cursor() as cursor:
                    # Table and column identifiers come only from this local,
                    # read-only archive's schema, never from user input.
                    source_columns_sql = ", ".join(
                        '"' + column.replace('"', '""') + '"' for column in columns
                    )
                    for row in source.execute(f"SELECT {source_columns_sql} FROM {table}"):
                        cursor.execute(query, tuple(row[column] for column in columns))
                        copied += cursor.rowcount
                print(f"{table}: inserted {copied} rows")
    finally:
        source.close()


if __name__ == "__main__":
    main()