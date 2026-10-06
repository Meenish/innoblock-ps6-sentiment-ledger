"""Off-chain store: full headlines, per-headline AI output, aggregated signals and the
exact analysis JSON whose keccak256 hash is written on-chain.
Postgres when DATABASE_URL is set (Neon/Supabase), otherwise a local SQLite file."""
import os
import sqlite3
import config

SQLITE_PATH = os.path.join(config.HERE, "sentiment.db")


def query(sql, params=()):
    """Run one statement. Write SQL with ? placeholders. Returns rows as dicts."""
    if config.DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
            cur = conn.execute(sql.replace("?", "%s"), params)
            return cur.fetchall() if cur.description else []
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS articles (
        id TEXT PRIMARY KEY, title TEXT, source TEXT, url TEXT,
        published_at BIGINT, tokens TEXT, origin TEXT)""",
    """CREATE TABLE IF NOT EXISTS signals (
        analysis_hash TEXT PRIMARY KEY, token TEXT, score INTEGER, confidence INTEGER,
        source_count INTEGER, observed_at BIGINT, label TEXT, method TEXT,
        analysis_json TEXT, tx_hash TEXT, block_number BIGINT, created_at BIGINT)""",
    "CREATE INDEX IF NOT EXISTS idx_signals_token ON signals (token, observed_at)",
    """CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY, started_at BIGINT, mode TEXT, status TEXT,
        message TEXT, tx_hash TEXT)""",
]


def init():
    for stmt in SCHEMA:
        query(stmt)


def save_article(a):
    query("""INSERT INTO articles (id, title, source, url, published_at, tokens, origin)
             VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO NOTHING""",
          (a["id"], a["title"], a["source"], a["url"], a["published_at"],
           ",".join(a["tokens"]), a["origin"]))


def save_signal(s, tx_hash, block_number, now):
    query("""INSERT INTO signals (analysis_hash, token, score, confidence, source_count,
             observed_at, label, method, analysis_json, tx_hash, block_number, created_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (analysis_hash) DO NOTHING""",
          (s["analysis_hash"], s["token"], s["score"], s["confidence"], s["source_count"],
           s["observed_at"], s["label"], s["method"], s["analysis_json"], tx_hash,
           block_number, now))
