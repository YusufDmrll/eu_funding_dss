import sqlite3
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "eu_funding.sqlite"
CSV_PATH = PROJECT_ROOT / "data" / "imports" / "calls_seed_clean.csv"

COLUMNS = [
    "call_id",
    "program",
    "pillar",
    "cluster",
    "call_title",
    "topic_title",
    "description",
    "objectives",
    "expected_impact",
    "action_type",
    "deadline_utc",
    "budget_min_eur",
    "budget_max_eur",
    "trl_min",
    "trl_max",
    "eligible_countries",
    "eligible_org_types",
    "consortium_required",
    "min_partners",
    "keywords",
    "source_url",
    "source_last_checked_utc",
]


def import_calls() -> int:
    print(f"Reading CSV from: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH, sep=";", encoding="utf-8-sig")

    cluster_map = {
        "Culture Creativity Society": "Culture, Creativity and Inclusive Society",
        "Climate Energy Mobility": "Climate, Energy and Mobility",
    }
    if "cluster" in df.columns:
        df["cluster"] = df["cluster"].replace(cluster_map)

    df = df[df["call_id"].notna()]
    df = df[df["call_title"].notna()]
    df = df[df["description"].fillna("").str.len() > 20]
    df = df[df["source_url"].notna()]
    df = df[df["deadline_utc"].notna()]

    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing columns: {missing}")

    df = df[COLUMNS].copy()

    df["budget_min_eur"] = pd.to_numeric(df["budget_min_eur"], errors="coerce")
    df["budget_max_eur"] = pd.to_numeric(df["budget_max_eur"], errors="coerce")
    df["trl_min"] = pd.to_numeric(df["trl_min"], errors="coerce")
    df["trl_max"] = pd.to_numeric(df["trl_max"], errors="coerce")
    df["min_partners"] = pd.to_numeric(df["min_partners"], errors="coerce")

    df["consortium_required"] = (
        df["consortium_required"]
        .astype(str)
        .str.strip()
        .str.lower()
        .map({"true": 1, "false": 0, "1": 1, "0": 0})
    )

    df["verified_status"] = "candidate"

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cols_for_insert = COLUMNS + ["verified_status", "updated_utc"]
    cols_sql = ", ".join(cols_for_insert)
    placeholders = ", ".join(["?"] * (len(COLUMNS) + 1)) + ", datetime('now')"

    update_cols = COLUMNS[1:] + ["verified_status"]
    update_sql = ", ".join([f"{c}=excluded.{c}" for c in update_cols])

    upsert_sql = f"""
    INSERT INTO funding_calls ({cols_sql})
    VALUES ({placeholders})
    ON CONFLICT(call_id) DO UPDATE SET
      {update_sql},
      updated_utc=datetime('now');
    """

    rows = []
    for _, row in df.iterrows():
        rows.append([
            row["call_id"],
            row["program"],
            row["pillar"],
            row["cluster"],
            row["call_title"],
            row["topic_title"],
            row["description"],
            row["objectives"],
            row["expected_impact"],
            row["action_type"],
            row["deadline_utc"],
            None if pd.isna(row["budget_min_eur"]) else float(row["budget_min_eur"]),
            None if pd.isna(row["budget_max_eur"]) else float(row["budget_max_eur"]),
            None if pd.isna(row["trl_min"]) else int(row["trl_min"]),
            None if pd.isna(row["trl_max"]) else int(row["trl_max"]),
            row["eligible_countries"],
            row["eligible_org_types"],
            None if pd.isna(row["consortium_required"]) else int(row["consortium_required"]),
            None if pd.isna(row["min_partners"]) else int(row["min_partners"]),
            row["keywords"],
            row["source_url"],
            row["source_last_checked_utc"],
            row["verified_status"],
        ])

    cur.executemany(upsert_sql, rows)

    conn.commit()
    conn.close()

    print(f"{len(rows)} calls upserted successfully.")
    return len(rows)


if __name__ == "__main__":
    import_calls()