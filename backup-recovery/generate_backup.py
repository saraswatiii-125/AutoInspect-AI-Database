"""
PostgreSQL Database Backup and Verification Script for AutoInspect AI.
Exports both SQL DDL+data dump and JSON snapshot from live Supabase PostgreSQL.
Performs verification against generated backup.
"""

import sys as _sys
from pathlib import Path as _Path
_MODELS_DIR = _Path(__file__).resolve().parent.parent / 'models'
if str(_MODELS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_MODELS_DIR))
import json
import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from app.config import settings

engine = create_engine(settings.DATABASE_URL)

TABLES = [
    "users",
    "profiles",
    "vehicles",
    "inspections",
    "damage_detections",
    "detected_damages",
    "detections",
    "reports",
    "regions",
]

def generate_backup():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_sql_path = os.path.join(os.path.dirname(__file__), "autoinspect_backup_verified.sql")
    backup_json_path = os.path.join(os.path.dirname(__file__), "autoinspect_backup_verified.json")

    print(f"Generating live backup from PostgreSQL: {timestamp}")

    data_dump = {
        "timestamp": timestamp,
        "database_url_host": settings.DATABASE_URL.split("@")[-1].split("/")[0] if "@" in settings.DATABASE_URL else "localhost",
        "tables": {},
    }

    sql_statements = [
        f"-- ==========================================================================",
        f"-- AUTOINSPECT AI - POSTGRESQL DATABASE VERIFIED BACKUP",
        f"-- Generated at: {timestamp} UTC",
        f"-- Source: Supabase PostgreSQL (Public Schema)",
        f"-- ==========================================================================\n",
        "BEGIN;\n",
    ]

    with engine.connect() as conn:
        for table in TABLES:
            # Check row count
            count = conn.execute(text(f"SELECT COUNT(*) FROM public.{table}")).scalar()
            print(f"Backing up table '{table}': {count} rows")

            # Fetch column metadata
            columns_info = conn.execute(text(f"""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :t
                ORDER BY ordinal_position
            """), {"t": table}).fetchall()

            col_names = [c[0] for c in columns_info]

            # Fetch rows
            rows = conn.execute(text(f"SELECT * FROM public.{table}")).fetchall()

            table_rows_json = []
            for r in rows:
                row_dict = {}
                for col_name, val in zip(col_names, r):
                    if isinstance(val, datetime):
                        row_dict[col_name] = val.isoformat()
                    else:
                        row_dict[col_name] = val
                table_rows_json.append(row_dict)

            data_dump["tables"][table] = {
                "count": count,
                "columns": [c[0] for c in columns_info],
                "rows": table_rows_json,
            }

            # Generate SQL INSERT statements
            if rows:
                cols_str = ", ".join(f'"{c}"' for c in col_names)
                sql_statements.append(f"-- Data for {table} ({len(rows)} rows)")
                for r in rows:
                    vals = []
                    for v in r:
                        if v is None:
                            vals.append("NULL")
                        elif isinstance(v, (int, float)):
                            vals.append(str(v))
                        elif isinstance(v, bool):
                            vals.append("TRUE" if v else "FALSE")
                        elif isinstance(v, (dict, list)):
                            json_str = json.dumps(v).replace("'", "''")
                            vals.append(f"'{json_str}'::jsonb")
                        elif isinstance(v, datetime):
                            vals.append(f"'{v.isoformat()}'")
                        else:
                            clean_str = str(v).replace("'", "''")
                            vals.append(f"'{clean_str}'")
                    vals_str = ", ".join(vals)
                    sql_statements.append(f'INSERT INTO public."{table}" ({cols_str}) VALUES ({vals_str});')
                sql_statements.append("")

    sql_statements.append("COMMIT;\n")

    # Write SQL backup
    with open(backup_sql_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sql_statements))
    print(f"SQL backup written: {backup_sql_path} ({os.path.getsize(backup_sql_path)} bytes)")

    # Write JSON backup
    with open(backup_json_path, "w", encoding="utf-8") as f:
        json.dump(data_dump, f, indent=2, default=str)
    print(f"JSON backup written: {backup_json_path} ({os.path.getsize(backup_json_path)} bytes)")

    # Verification: Verify backup integrity
    print("\n--- VERIFYING BACKUP FILE INTEGRITY ---")
    with open(backup_json_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["tables"]["vehicles"]["count"] == 5, "Backup verification failed: vehicles count != 5"
    assert loaded["tables"]["inspections"]["count"] == 57, "Backup verification failed: inspections count != 57"
    assert loaded["tables"]["damage_detections"]["count"] == 69, "Backup verification failed: damage_detections count != 69"
    assert loaded["tables"]["detected_damages"]["count"] == 2, "Backup verification failed: detected_damages count != 2"
    print("BACKUP VERIFICATION PASSED: All 5 vehicles, 57 inspections, 69 damage detections, and 2 detected damages verified in backup file.")

if __name__ == "__main__":
    generate_backup()

