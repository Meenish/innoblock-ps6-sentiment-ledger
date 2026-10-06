"""One-off: copy your local SQLite history (sentiment.db) into a Postgres database (Neon).

Usage (from the backend folder, venv active):
    python migrate_to_postgres.py "postgresql://user:password@host/dbname?sslmode=require"

Safe to run more than once: rows that already exist are skipped. The connection string is
never printed or saved.
"""
import os
import sqlite3
import sys

import config

TABLES = {
    "articles": ["id", "title", "source", "url", "published_at", "tokens", "origin"],
    "signals": ["analysis_hash", "token", "score", "confidence", "source_count", "observed_at",
                "label", "method", "analysis_json", "tx_hash", "block_number", "created_at"],
    "runs": ["id", "started_at", "mode", "status", "message", "tx_hash"],
}
KEYS = {"articles": "id", "signals": "analysis_hash", "runs": "id"}


def main():
    if len(sys.argv) != 2 or not sys.argv[1].startswith(("postgres://", "postgresql://")):
        sys.exit('Usage: python migrate_to_postgres.py "postgresql://user:password@host/db?sslmode=require"')
    config.DATABASE_URL = sys.argv[1]
    import db  # imported after DATABASE_URL is set, so it talks to Postgres

    src_path = db.SQLITE_PATH
    if not os.path.exists(src_path):
        sys.exit(f"No local database found at {src_path}. Run the backend once first.")
    src = sqlite3.connect(src_path)
    src.row_factory = sqlite3.Row

    db.init()  # creates the tables in Postgres if they do not exist
    for table, cols in TABLES.items():
        rows = src.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
        before = db.query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
        for r in rows:
            db.query(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
                     f"ON CONFLICT ({KEYS[table]}) DO NOTHING", tuple(r[c] for c in cols))
        after = db.query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
        print(f"{table}: {len(rows)} local rows, {after - before} copied, {after} now in Postgres")
    src.close()


if __name__ == "__main__":
    main()
