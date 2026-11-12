"""
Extract exact DDL for public schema tables from production PostgreSQL.
Generates schema_ddl.sql containing CREATE TABLE, PK, FK, CHECK, and INDEX statements.
"""

import sys as _sys
from pathlib import Path as _Path
_MODELS_DIR = _Path(__file__).resolve().parent.parent / 'models'
if str(_MODELS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_MODELS_DIR))
from sqlalchemy import create_engine, text
from app.config import settings

prod_engine = create_engine(settings.DATABASE_URL)

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

def extract_schema_ddl():
    ddl_statements = [
        "-- ==========================================================================",
        "-- AUTOINSPECT AI - DDL SCHEMA DEFINITION",
        "-- Extracted from live production PostgreSQL for test database restoration",
        "-- ==========================================================================\n",
        "CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";\n"
    ]

    with prod_engine.connect() as conn:
        # 1. Sequences
        seqs = conn.execute(text("""
            SELECT sequence_name FROM information_schema.sequences
            WHERE sequence_schema = 'public';
        """)).fetchall()
        for seq in seqs:
            ddl_statements.append(f'CREATE SEQUENCE IF NOT EXISTS public."{seq[0]}";')
        ddl_statements.append("")

        # 2. Table definitions with columns
        for tbl in TABLES:
            cols = conn.execute(text("""
                SELECT 
                    column_name, 
                    data_type, 
                    character_maximum_length,
                    column_default,
                    is_nullable,
                    udt_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :t
                ORDER BY ordinal_position;
            """), {"t": tbl}).fetchall()

            col_defs = []
            for c in cols:
                c_name, c_type, c_len, c_def, c_null, udt = c
                type_str = udt.upper()
                if udt in ("varchar", "character varying") and c_len:
                    type_str = f"VARCHAR({c_len})"
                elif udt == "int4":
                    type_str = "INTEGER"
                elif udt == "int8":
                    type_str = "BIGINT"
                elif udt == "numeric":
                    type_str = "NUMERIC"
                elif udt == "float8":
                    type_str = "DOUBLE PRECISION"
                elif udt == "float4":
                    type_str = "REAL"
                elif udt == "timestamp":
                    type_str = "TIMESTAMP WITHOUT TIME ZONE"
                elif udt == "timestamptz":
                    type_str = "TIMESTAMP WITH TIME ZONE"
                elif udt == "jsonb":
                    type_str = "JSONB"
                elif udt == "uuid":
                    type_str = "UUID"
                elif udt == "text":
                    type_str = "TEXT"

                null_str = "NULL" if c_null == "YES" else "NOT NULL"
                def_str = f"DEFAULT {c_def}" if c_def else ""

                parts = [f'"{c_name}"', type_str, def_str, null_str]
                col_defs.append("    " + " ".join(p for p in parts if p))

            ddl_statements.append(f'CREATE TABLE IF NOT EXISTS public."{tbl}" (')
            ddl_statements.append(",\n".join(col_defs))
            ddl_statements.append(");\n")

        # 3. Primary Keys
        pks = conn.execute(text("""
            SELECT tc.table_name, tc.constraint_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = 'public'
            ORDER BY tc.table_name;
        """)).fetchall()
        for pk in pks:
            if pk[0] in TABLES:
                ddl_statements.append(f'ALTER TABLE ONLY public."{pk[0]}" ADD CONSTRAINT "{pk[1]}" PRIMARY KEY ("{pk[2]}");')
        ddl_statements.append("")

        # 4. Unique Constraints
        uniques = conn.execute(text("""
            SELECT tc.table_name, tc.constraint_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'UNIQUE'
              AND tc.table_schema = 'public'
            ORDER BY tc.table_name;
        """)).fetchall()
        for u in uniques:
            if u[0] in TABLES:
                ddl_statements.append(f'ALTER TABLE ONLY public."{u[0]}" ADD CONSTRAINT "{u[1]}" UNIQUE ("{u[2]}");')
        ddl_statements.append("")

        # 5. Check Constraints
        checks = conn.execute(text("""
            SELECT tc.table_name, tc.constraint_name, cc.check_clause
            FROM information_schema.table_constraints tc
            JOIN information_schema.check_constraints cc
              ON tc.constraint_name = cc.constraint_name
              AND tc.constraint_schema = cc.constraint_schema
            WHERE tc.constraint_type = 'CHECK'
              AND tc.table_schema = 'public'
              AND tc.constraint_name NOT LIKE '%_not_null'
            ORDER BY tc.table_name;
        """)).fetchall()
        for chk in checks:
            if chk[0] in TABLES:
                not_valid = " NOT VALID" if chk[1] == "inspections_vehicle_id_required" else ""
                ddl_statements.append(f'ALTER TABLE ONLY public."{chk[0]}" ADD CONSTRAINT "{chk[1]}" CHECK ({chk[2]}){not_valid};')
        ddl_statements.append("")

        # 6. Foreign Keys
        fks = conn.execute(text("""
            SELECT
                tc.table_name,
                tc.constraint_name,
                kcu.column_name,
                ccu.table_name AS foreign_table,
                ccu.column_name AS foreign_column,
                rc.delete_rule,
                rc.update_rule
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
            JOIN information_schema.referential_constraints rc
              ON rc.constraint_name = tc.constraint_name
              AND rc.constraint_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
            ORDER BY tc.table_name, tc.constraint_name;
        """)).fetchall()
        for fk in fks:
            if fk[0] in TABLES and fk[3] in TABLES:
                del_action = f"ON DELETE {fk[5]}" if fk[5] else ""
                upd_action = f"ON UPDATE {fk[6]}" if fk[6] else ""
                ddl_statements.append(f'ALTER TABLE ONLY public."{fk[0]}" ADD CONSTRAINT "{fk[1]}" FOREIGN KEY ("{fk[2]}") REFERENCES public."{fk[3]}" ("{fk[4]}") {del_action} {upd_action};')
        ddl_statements.append("")

        # 7. Indexes
        indexes = conn.execute(text("""
            SELECT
                t.relname AS table_name,
                i.relname AS index_name,
                pg_get_indexdef(ix.indexrelid) AS index_def
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
              AND t.relname = ANY(:tables)
              AND NOT ix.indisprimary
              AND NOT ix.indisunique
            ORDER BY t.relname, i.relname;
        """), {"tables": TABLES}).fetchall()
        for idx in indexes:
            ddl_statements.append(f"{idx[2]};")

    ddl_content = "\n".join(ddl_statements)
    with open("schema_ddl.sql", "w", encoding="utf-8") as f:
        f.write(ddl_content)
    print(f"Schema DDL extracted: schema_ddl.sql ({len(ddl_content)} chars)")

if __name__ == "__main__":
    extract_schema_ddl()

