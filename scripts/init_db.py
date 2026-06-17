import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "eu_funding.sqlite"


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS funding_calls (
        call_id TEXT PRIMARY KEY,
        program TEXT NOT NULL,
        pillar TEXT,
        cluster TEXT,
        call_title TEXT NOT NULL,
        topic_title TEXT,
        description TEXT,
        objectives TEXT,
        expected_impact TEXT,
        action_type TEXT,
        deadline_utc TEXT,
        budget_min_eur REAL,
        budget_max_eur REAL,
        trl_min INTEGER,
        trl_max INTEGER,
        eligible_countries TEXT,
        eligible_org_types TEXT,
        consortium_required INTEGER,
        min_partners INTEGER,
        keywords TEXT,
        source_url TEXT NOT NULL,
        source_last_checked_utc TEXT,
        verified_status TEXT DEFAULT 'candidate',
        created_utc TEXT DEFAULT (datetime('now')),
        updated_utc TEXT
    )
    """)

    conn.commit()
    conn.close()
    print(f"Database initialized successfully: {DB_PATH}")


if __name__ == "__main__":
    init_db()