"""Load NHTSA CRSS 2023 CSVs into the local DuckDB file.

Run: .venv/bin/python scripts/load_crss.py

The CSVs live at data/raw/crss2023/CRSS2023CSV/.
Loads every CSV into schema `crss2023`, table name = lowercased file stem.
"""
from __future__ import annotations

from pathlib import Path
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = PROJECT_ROOT / "data" / "raw" / "crss2023" / "CRSS2023CSV"
DB_PATH = PROJECT_ROOT / "data" / "fars.duckdb"


def main() -> None:
    if not CSV_DIR.exists():
        raise SystemExit(f"CRSS CSV dir not found: {CSV_DIR}")

    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS crss2023;")

    csvs = sorted(CSV_DIR.glob("*.csv")) + sorted(CSV_DIR.glob("*.CSV"))
    print(f"Loading {len(csvs)} CSVs from {CSV_DIR} -> {DB_PATH}")

    for csv in csvs:
        table = f"crss2023.{csv.stem.lower()}"
        con.execute(f"DROP TABLE IF EXISTS {table};")
        con.execute(
            f"CREATE TABLE {table} AS "
            f"SELECT * FROM read_csv_auto('{csv}', ignore_errors=true, sample_size=-1);"
        )
        n = con.execute(f"SELECT COUNT(*) FROM {table};").fetchone()[0]
        print(f"  {table}: {n:,} rows")

    con.close()
    print(f"\nDone. DB at {DB_PATH}")


if __name__ == "__main__":
    main()
