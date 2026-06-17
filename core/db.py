import sqlite3
from pathlib import Path
from typing import List, Tuple, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "eu_funding.sqlite"


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def count_calls() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM funding_calls")
    (cnt,) = cur.fetchone()
    conn.close()
    return int(cnt)


def fetch_calls(limit: int = 500) -> List[Tuple[Any, ...]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          call_id,
          program,
          pillar,
          cluster,
          call_title,
          deadline_utc,
          trl_min,
          trl_max,
          source_url,
          verified_status
        FROM funding_calls
        ORDER BY deadline_utc
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def run_seed_import() -> int:
    from scripts.import_calls import import_calls
    return import_calls()