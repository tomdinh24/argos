"""Load NHTSA FARS 2023 CSVs into a local DuckDB file.

Run: .venv/bin/python scripts/load_fars.py

The CSVs live at data/raw/fars2023/FARS2023NationalCSV/.
We load every CSV in the directory as a table named after the file (lowercased),
into data/fars.duckdb under the schema `fars2023`.
"""
from __future__ import annotations

from pathlib import Path
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = PROJECT_ROOT / "data" / "raw" / "fars2023" / "FARS2023NationalCSV"
DB_PATH = PROJECT_ROOT / "data" / "fars.duckdb"


def main() -> None:
    if not CSV_DIR.exists():
        raise SystemExit(f"FARS CSV dir not found: {CSV_DIR}")

    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS fars2023;")

    csvs = sorted(CSV_DIR.glob("*.csv")) + sorted(CSV_DIR.glob("*.CSV"))
    print(f"Loading {len(csvs)} CSVs from {CSV_DIR} -> {DB_PATH}")

    for csv in csvs:
        table = f"fars2023.{csv.stem.lower()}"
        # read_csv_auto handles header detection, type inference, and most quoting weirdness.
        # We use IGNORE_ERRORS to keep going past the occasional malformed row that NHTSA ships.
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
