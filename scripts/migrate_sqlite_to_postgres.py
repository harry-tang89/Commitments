#!/usr/bin/env python3
"""Copy app data from a SQLite database into PostgreSQL."""

from __future__ import annotations

import argparse
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psycopg2
from psycopg2.extras import execute_values


TABLE_ORDER = ("user", "commitment", "commitment_collaborator", "study_log")
SEQUENCES = {
    "user": "user_id_seq",
    "commitment": "commitment_id_seq",
    "study_log": "study_log_id_seq",
}


@dataclass(frozen=True)
class TableCopyPlan:
    name: str
    columns: tuple[str, ...]


COPY_PLANS = (
    TableCopyPlan(
        name="user",
        columns=("id", "username", "email", "password_hash", "birth_day", "birth_month", "birth_year"),
    ),
    TableCopyPlan(
        name="commitment",
        columns=("id", "user_id", "title", "description", "deadline_date", "status", "created_at", "category"),
    ),
    TableCopyPlan(
        name="commitment_collaborator",
        columns=("commitment_id", "user_id"),
    ),
    TableCopyPlan(
        name="study_log",
        columns=("id", "user_id", "log_date", "minutes", "note", "created_at"),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite-path",
        default="app/app.db",
        help="Path to the source SQLite database.",
    )
    parser.add_argument(
        "--postgres-url",
        default=os.environ.get("DATABASE_URL"),
        help="Target PostgreSQL connection URL. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--allow-nonempty",
        action="store_true",
        help="Allow importing into PostgreSQL even if target tables already contain rows.",
    )
    return parser.parse_args()


def fetch_rows(connection: sqlite3.Connection, table: str, columns: Iterable[str]) -> list[tuple]:
    column_sql = ", ".join(f'"{column}"' for column in columns)
    cursor = connection.execute(f'SELECT {column_sql} FROM "{table}" ORDER BY 1')
    return cursor.fetchall()


def ensure_sqlite_exists(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"SQLite database not found: {path}")


def ensure_postgres_url(url: str | None) -> str:
    if not url:
        raise SystemExit("PostgreSQL URL is required. Set DATABASE_URL or pass --postgres-url.")
    if not url.startswith("postgresql://"):
        raise SystemExit(f"Expected a PostgreSQL URL, got: {url}")
    return url


def ensure_target_empty(pg_cursor, allow_nonempty: bool) -> None:
    if allow_nonempty:
        return

    nonempty_tables: list[str] = []
    for table in TABLE_ORDER:
        pg_cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
        row_count = pg_cursor.fetchone()[0]
        if row_count:
            nonempty_tables.append(f"{table}={row_count}")

    if nonempty_tables:
        joined = ", ".join(nonempty_tables)
        raise SystemExit(
            "Target PostgreSQL database is not empty. "
            f"Found rows in: {joined}. Re-run with --allow-nonempty if that is intentional."
        )


def insert_rows(pg_cursor, table: str, columns: tuple[str, ...], rows: list[tuple]) -> None:
    if not rows:
        return

    column_sql = ", ".join(f'"{column}"' for column in columns)
    sql = f'INSERT INTO "{table}" ({column_sql}) VALUES %s'
    execute_values(pg_cursor, sql, rows, page_size=500)


def reset_sequences(pg_cursor) -> None:
    for table, sequence in SEQUENCES.items():
        pg_cursor.execute(f'SELECT COALESCE(MAX(id), 0) FROM "{table}"')
        max_id = pg_cursor.fetchone()[0]
        if max_id > 0:
            pg_cursor.execute("SELECT setval(%s, %s, %s)", (sequence, max_id, True))
        else:
            pg_cursor.execute("SELECT setval(%s, %s, %s)", (sequence, 1, False))


def main() -> None:
    args = parse_args()
    sqlite_path = Path(args.sqlite_path)
    ensure_sqlite_exists(sqlite_path)
    postgres_url = ensure_postgres_url(args.postgres_url)
    copied_counts: dict[str, int] = {}

    sqlite_connection = sqlite3.connect(sqlite_path)
    sqlite_connection.row_factory = None

    try:
        with psycopg2.connect(postgres_url) as pg_connection:
            with pg_connection.cursor() as pg_cursor:
                ensure_target_empty(pg_cursor, args.allow_nonempty)

                for plan in COPY_PLANS:
                    rows = fetch_rows(sqlite_connection, plan.name, plan.columns)
                    insert_rows(pg_cursor, plan.name, plan.columns, rows)
                    copied_counts[plan.name] = len(rows)

                reset_sequences(pg_cursor)

            pg_connection.commit()
    finally:
        sqlite_connection.close()

    for table in TABLE_ORDER:
        print(f"{table}: copied {copied_counts.get(table, 0)} rows")


if __name__ == "__main__":
    main()
