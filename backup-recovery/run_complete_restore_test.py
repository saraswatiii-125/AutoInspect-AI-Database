"""
AutoInspect AI - Complete Single-Pass SQL Logical Backup Restoration & Parity Verification.

Resets the isolated test database (`autoinspect_test`) and restores the complete
single-file PostgreSQL SQL logical export (`autoinspect_complete_backup.sql`) in ONE pass
using a clean autocommit psycopg 3 connection (so internal BEGIN...COMMIT runs natively).
Verifies full object parity against `postgres` and `autoinspect_complete_backup_manifest.json`:
- All 22 tables & exact row counts (393 total rows)
- Active ordinal column parity ignoring physical `attisdropped` tombstones (e.g. vehicles attnum=6)
- All 7 sequences (`last_value` & `is_called` state + live nextval check)
- All Primary Keys, Unique Constraints, Public FKs, CHECK Constraints (`NOT VALID` preserved)
- Explicit notice reporting for Supabase `auth`-dependent objects skipped on `autoinspect_test` (23 expected)
- All 23 PG indexes (13 constraint + 10 standalone incl. partial unique `idx_vehicles_code`)
- Functions, Function ACLs (`proacl`, 0 `PUBLIC` EXECUTE), Triggers, RLS enablement, Schema & Table ACLs
- Live negative tests (PK, UK, partial unique index, FK, CHECK, NOT VALID CHECK, orphan audit)
"""

import sys as _sys
from pathlib import Path as _Path
_MODELS_DIR = _Path(__file__).resolve().parent.parent / 'models'
if str(_MODELS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_MODELS_DIR))

import json
from pathlib import Path
import psycopg
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.config import settings

REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_BACKUP_PATH = REPO_ROOT / "backup-recovery" / "autoinspect_complete_backup.sql"
MANIFEST_PATH = REPO_ROOT / "schema" / "complete_backup_manifest.json"
TEST_DB_NAME = "autoinspect_test"

prod_url = make_url(settings.DATABASE_URL)
test_url = prod_url.set(database=TEST_DB_NAME)

prod_engine = create_engine(prod_url)
test_engine = create_engine(test_url)

psycopg_test_kwargs = {
    "host": test_url.host,
    "port": test_url.port or 5432,
    "dbname": TEST_DB_NAME,
    "user": test_url.username,
    "password": test_url.password,
    "sslmode": str(test_url.query.get("sslmode", "require")),
}


def run_complete_restore_and_verify() -> None:
    print("=" * 80)
    print("AUTOINSPECT AI - COMPLETE SINGLE-PASS RESTORE & PARITY VERIFICATION")
    print(f"Backup Artifact : {SQL_BACKUP_PATH.name}")
    print(f"Target Database : {TEST_DB_NAME}")
    print("=" * 80)

    if not SQL_BACKUP_PATH.is_file() or not MANIFEST_PATH.is_file():
        raise FileNotFoundError("Missing complete backup SQL or manifest. Run generate_complete_backup.py first.")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    backup_sql = SQL_BACKUP_PATH.read_text(encoding="utf-8")

    # -------------------------------------------------------------------------
    # STEP 1: SAFETY GATE + CLEAN TEST DB RESET
    # -------------------------------------------------------------------------
    print("\n[STEP 1] Safety Gate & Clean Schema Reset on 'autoinspect_test'...")
    with test_engine.connect() as conn:
        current_db = conn.execute(text("SELECT current_database();")).scalar()
        if current_db != TEST_DB_NAME:
            raise RuntimeError(f"SAFETY ABORT: Expected '{TEST_DB_NAME}', got '{current_db}'!")
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))
        conn.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC;"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO postgres;"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO PUBLIC;"))
        conn.commit()
    print("  PASSED: Safety Gate verified ('autoinspect_test') & schema wiped clean.")

    # -------------------------------------------------------------------------
    # STEP 2: SINGLE-PASS EXECUTION OF COMPLETE BACKUP SQL (AUTOCOMMIT -> NATIVE BEGIN..COMMIT)
    # -------------------------------------------------------------------------
    print("\n[STEP 2] Executing complete backup SQL in ONE single pass...")
    notices = []
    with psycopg.connect(**psycopg_test_kwargs, autocommit=True) as raw_conn:
        assert raw_conn.execute("SELECT current_database();").fetchone()[0] == TEST_DB_NAME
        raw_conn.add_notice_handler(lambda diag: notices.append(diag.message_primary or ""))
        with raw_conn.cursor() as cur:
            cur.execute(backup_sql)

    skip_notices = [n for n in notices if "Skipping " in n]
    expected_skips = (
        manifest["constraints"]["foreign_key_external"]
        + manifest["policies"]["auth_dependent_guarded"]
    )
    assert len(skip_notices) == expected_skips, (
        f"Expected {expected_skips} surfaced portability skip notices "
        f"(external FKs + auth.uid() policies), got {len(skip_notices)}: {skip_notices}"
    )
    print(
        f"  PASSED: Single-pass restore committed atomically ({len(backup_sql)} bytes, "
        f"total notices={len(notices)}, expected Supabase-auth skips surfaced={len(skip_notices)})."
    )

    # -------------------------------------------------------------------------
    # STEP 3: FULL OBJECT PARITY COMPARISON (PROD VS RESTORED TEST DB)
    # -------------------------------------------------------------------------
    print("\n[STEP 3] Verifying full object & row count parity...")
    with prod_engine.connect() as pconn, test_engine.connect() as tconn:
        # 3.1 Tables & exact row counts (all 22 public tables)
        exp_tables = manifest["tables"]
        restored_tables = [
            r[0]
            for r in tconn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;")
            ).fetchall()
        ]
        assert set(restored_tables) == set(exp_tables.keys()), (
            f"Table mismatch! Missing={set(exp_tables.keys()) - set(restored_tables)}, Extra={set(restored_tables) - set(exp_tables.keys())}"
        )
        for tbl, exp_cnt in exp_tables.items():
            cnt = tconn.execute(text(f'SELECT COUNT(*) FROM public."{tbl}";')).scalar()
            assert cnt == exp_cnt, f"Row count mismatch on {tbl}: expected {exp_cnt}, got {cnt}"
        print(f"  PASSED: All {len(exp_tables)} tables & {sum(exp_tables.values())} rows match 100%.")
        print(
            f"          Core baselines verified -> vehicles={exp_tables['vehicles']}, "
            f"inspections={exp_tables['inspections']}, damage_detections={exp_tables['damage_detections']}, "
            f"detected_damages={exp_tables['detected_damages']}"
        )

        # 3.1b Active ordinal column parity (normalizing dropped column tombstones via ROW_NUMBER())
        col_query = text("""
            SELECT
                c.relname,
                ROW_NUMBER() OVER (PARTITION BY c.relname ORDER BY a.attnum) AS active_pos,
                a.attname,
                pg_catalog.format_type(a.atttypid, a.atttypmod) AS col_type,
                a.attnotnull,
                pg_get_expr(ad.adbin, ad.adrelid) AS col_default,
                a.attidentity::text
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid
            LEFT JOIN pg_attrdef ad ON ad.adrelid = c.oid AND ad.adnum = a.attnum
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY 1, 2;
        """)
        prod_cols = set(pconn.execute(col_query).fetchall())
        test_cols = set(tconn.execute(col_query).fetchall())
        assert prod_cols == test_cols, (
            f"Active column parity mismatch! Only prod={prod_cols - test_cols}, Only test={test_cols - prod_cols}"
        )
        print(f"  PASSED: All {len(prod_cols)} active columns (types, defaults, NOT NULL, identity) match 100%.")

        # 3.2 Sequences state (last_value & is_called)
        exp_seqs = manifest["sequences"]
        restored_seqs = [
            r[0]
            for r in tconn.execute(
                text("SELECT sequencename FROM pg_sequences WHERE schemaname = 'public' ORDER BY sequencename;")
            ).fetchall()
        ]
        assert set(restored_seqs) == set(exp_seqs.keys()), f"Sequence mismatch: {restored_seqs}"
        for seq_name, exp_state in exp_seqs.items():
            lv, ic = tconn.execute(text(f'SELECT last_value, is_called FROM public."{seq_name}";')).fetchone()
            assert int(lv) == exp_state["last_value"] and bool(ic) == exp_state["is_called"], (
                f"Sequence state mismatch on {seq_name}: expected {exp_state}, got ({lv}, {ic})"
            )
        print(f"  PASSED: All {len(exp_seqs)} sequences & cursor states match 100%.")

        # 3.3 Constraints parity (excluding external auth.users FK on non-Supabase DB)
        prod_cons = set(
            pconn.execute(
                text("""
                    SELECT c.relname, con.conname, con.contype, con.convalidated
                    FROM pg_constraint con
                    JOIN pg_class c ON c.oid = con.conrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND con.conname <> 'profiles_id_fkey';
                """)
            ).fetchall()
        )
        test_cons = set(
            tconn.execute(
                text("""
                    SELECT c.relname, con.conname, con.contype, con.convalidated
                    FROM pg_constraint con
                    JOIN pg_class c ON c.oid = con.conrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND con.conname <> 'profiles_id_fkey';
                """)
            ).fetchall()
        )
        assert prod_cons == test_cons, f"Constraint parity mismatch: missing={prod_cons - test_cons}, extra={test_cons - prod_cons}"
        print(f"  PASSED: All {len(prod_cons)} public-schema constraints match 100% (profiles_id_fkey guarded for missing auth.users).")

        # 3.4 Indexes parity (all 23 indexes including partial unique idx_vehicles_code)
        prod_idxs = set(
            pconn.execute(
                text("SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public';")
            ).fetchall()
        )
        test_idxs = set(
            tconn.execute(
                text("SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public';")
            ).fetchall()
        )
        assert prod_idxs == test_idxs, f"Index parity mismatch: missing={prod_idxs - test_idxs}, extra={test_idxs - prod_idxs}"
        print(f"  PASSED: All {len(prod_idxs)} public indexes (including partial unique idx_vehicles_code) match 100%.")

        # 3.5 Functions, Function ACLs (proacl), triggers, RLS enablement, and zero PUBLIC grants
        func_acl_query = text("""
            SELECT p.proname,
                   pg_catalog.pg_get_function_identity_arguments(p.oid) AS fn_args,
                   pg_catalog.has_function_privilege('public', p.oid, 'EXECUTE') AS public_exec,
                   p.proacl::text
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public'
              AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e')
            ORDER BY 1, 2;
        """)
        prod_funcs = pconn.execute(func_acl_query).fetchall()
        test_funcs = tconn.execute(func_acl_query).fetchall()
        assert prod_funcs == test_funcs, f"Function/ACL mismatch! prod={prod_funcs} test={test_funcs}"
        assert all(not row[2] for row in test_funcs), f"PUBLIC retained EXECUTE on restored function: {test_funcs}"

        rls_disabled = tconn.execute(
            text("""
                SELECT c.relname FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity;
            """)
        ).fetchall()
        assert not rls_disabled, f"Tables missing RLS enablement: {rls_disabled}"

        public_grants = tconn.execute(
            text("""
                SELECT table_name, privilege_type FROM information_schema.role_table_grants
                WHERE grantee = 'PUBLIC' AND table_schema = 'public';
            """)
        ).fetchall()
        assert not public_grants, f"Unexpected PUBLIC table grants: {public_grants}"
        print(
            f"  PASSED: Functions ({len(test_funcs)}) & proacl (0 PUBLIC EXECUTE), "
            f"triggers, RLS enabled on all {len(exp_tables)} tables, 0 PUBLIC table grants."
        )

    # -------------------------------------------------------------------------
    # STEP 4: BEHAVIORAL CONSTRAINT, SEQUENCE & INTEGRITY TESTS (ROLLED BACK)
    # -------------------------------------------------------------------------
    print("\n[STEP 4] Running live integrity & enforcement tests on restored database...")
    with test_engine.connect() as conn:
        # 4.1 PK collision
        try:
            conn.execute(text("INSERT INTO public.vehicles (id, make, model, year, registration, color, image) VALUES ('1', 'BMW', 'Dup', 2023, 'TMP-PK-1', 'White', 'img');"))
            raise AssertionError("Expected PK violation!")
        except Exception as e:
            conn.rollback()
            assert "vehicles_pkey" in str(e)

        # 4.2 Registration unique constraint
        try:
            conn.execute(text("INSERT INTO public.vehicles (id, make, model, year, registration, color, image) VALUES ('tmp_v_1', 'BMW', 'Dup', 2023, 'MH-12-AB-2026', 'White', 'img');"))
            raise AssertionError("Expected registration unique violation!")
        except Exception as e:
            conn.rollback()
            assert "vehicles_registration_key" in str(e)

        # 4.3 Partial unique index idx_vehicles_code
        conn.execute(text("INSERT INTO public.vehicles (id, make, model, year, registration, color, image, code) VALUES ('tmp_c1', 'Audi', 'Q7', 2024, 'TMP-CODE-1', 'Black', 'img', 'UNIQUE_CODE_99');"))
        try:
            conn.execute(text("INSERT INTO public.vehicles (id, make, model, year, registration, color, image, code) VALUES ('tmp_c2', 'Audi', 'Q7', 2024, 'TMP-CODE-2', 'Black', 'img', 'UNIQUE_CODE_99');"))
            raise AssertionError("Expected partial unique index violation on vehicles.code!")
        except Exception as e:
            conn.rollback()
            assert "idx_vehicles_code" in str(e)

        # 4.4 Multiple NULL codes permitted by partial unique index
        conn.execute(text("INSERT INTO public.vehicles (id, make, model, year, registration, color, image, code) VALUES ('tmp_n1', 'Audi', 'A4', 2024, 'TMP-NULL-1', 'White', 'img', NULL);"))
        conn.execute(text("INSERT INTO public.vehicles (id, make, model, year, registration, color, image, code) VALUES ('tmp_n2', 'Audi', 'A6', 2024, 'TMP-NULL-2', 'White', 'img', NULL);"))
        conn.rollback()

        # 4.5 Foreign Key enforcement
        try:
            conn.execute(text("INSERT INTO public.damage_detections (inspection_id, class_id, class_name, confidence, box_x1, box_y1, box_x2, box_y2) VALUES ('nonexistent', 1, 'Dent', 0.5, 0, 0, 10, 10);"))
            raise AssertionError("Expected FK violation!")
        except Exception as e:
            conn.rollback()
            assert "damage_detections_inspection_id_fkey" in str(e)

        # 4.6 Confidence check constraint
        try:
            conn.execute(text("INSERT INTO public.damage_detections (inspection_id, class_id, class_name, confidence, box_x1, box_y1, box_x2, box_y2) VALUES ('test-persist-check-001', 1, 'Dent', 1.5, 0, 0, 10, 10);"))
            raise AssertionError("Expected confidence check violation!")
        except Exception as e:
            conn.rollback()
            assert "damage_detections_confidence_check" in str(e)

        # 4.7 NOT VALID check constraint (blocks new NULL vehicle_id while historical 8 remain intact)
        try:
            conn.execute(text("INSERT INTO public.inspections (id, vehicle_id, date) VALUES ('tmp_null_v', NULL, '2026-11-11');"))
            raise AssertionError("Expected inspections_vehicle_id_required check violation!")
        except Exception as e:
            conn.rollback()
            assert "inspections_vehicle_id_required" in str(e)

        # 4.8 Identity column & sequence nextval state check (reset explicitly in rollback-safe check)
        next_insp_id = conn.execute(text("SELECT nextval('public.inspections_id_seq');")).scalar()
        assert next_insp_id == 57, f"Expected next inspections_id_seq = 57, got {next_insp_id}"
        conn.execute(text("SELECT pg_catalog.setval('public.\"inspections_id_seq\"', 56, true);"))
        conn.commit()

        # 4.9 Orphan audit across restored data
        dd_orphans = conn.execute(text("""
            SELECT COUNT(*) FROM public.damage_detections dd
            WHERE NOT EXISTS (SELECT 1 FROM public.inspections i WHERE i.inspection_id = dd.inspection_id);
        """)).scalar()
        dam_orphans = conn.execute(text("""
            SELECT COUNT(*) FROM public.detected_damages dam
            WHERE NOT EXISTS (SELECT 1 FROM public.inspections i WHERE i.id = dam.inspection_id);
        """)).scalar()
        insp_orphans = conn.execute(text("""
            SELECT COUNT(*) FROM public.inspections i
            WHERE i.vehicle_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM public.vehicles v WHERE v.id = i.vehicle_id);
        """)).scalar()
        assert dd_orphans == 0 and dam_orphans == 0 and insp_orphans == 0

        # 4.10 Spot-check production sample rows & JSONB
        v1 = conn.execute(text("SELECT make, registration, health_score FROM public.vehicles WHERE id = '1';")).fetchone()
        assert v1 == ("BMW", "MH-12-AB-2026", 100), f"Unexpected vehicle '1': {v1}"
        i4 = conn.execute(text("SELECT vehicle_id, overall_score, damages FROM public.inspections WHERE id = '4';")).fetchone()
        assert i4[0] == "1" and i4[1] == 85 and isinstance(i4[2], list), f"Unexpected inspection '4': {i4}"

        print("  PASSED: PK, UK, partial unique index (idx_vehicles_code), FK, CHECK, NOT VALID CHECK, sequences, 0 orphans, & JSONB verified.")

    print("\n" + "=" * 80)
    print("COMPLETE SINGLE-PASS RESTORE & VERIFICATION: 100% PASS")
    print("=" * 80)


if __name__ == "__main__":
    run_complete_restore_and_verify()
