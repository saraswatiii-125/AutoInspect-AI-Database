"""
AutoInspect AI - Comprehensive Database Backup Restoration & Verification Engine.
Executes an actual restoration into 'autoinspect_test' and validates all integrity constraints.
"""

import sys as _sys
from pathlib import Path as _Path
_MODELS_DIR = _Path(__file__).resolve().parent.parent / 'models'
if str(_MODELS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_MODELS_DIR))
import os
import json
from sqlalchemy import create_engine, text
from pathlib import Path
from app.config import settings

# Safety checks
assert "postgres" in settings.DATABASE_URL, "Production URL invalid"
TEST_DB_NAME = "autoinspect_test"
TEST_DATABASE_URL = settings.DATABASE_URL.rsplit('/', 1)[0] + '/' + TEST_DB_NAME

print("=" * 80)
print("AUTOINSPECT AI - DATABASE BACKUP RESTORATION & INTEGRITY VERIFICATION")
print(f"Target Database: {TEST_DB_NAME}")
print("=" * 80)

test_engine = create_engine(TEST_DATABASE_URL)

def run_full_restoration_and_verification():
    # -------------------------------------------------------------------------
    # STEP 1: SAFETY GATE VERIFICATION
    # -------------------------------------------------------------------------
    print("\n[STEP 1] SAFETY GATE: Verifying target database identity...")
    with test_engine.connect() as conn:
        current_db = conn.execute(text("SELECT current_database();")).scalar()
        print(f"  Connected database: '{current_db}'")
        if current_db != TEST_DB_NAME:
            raise RuntimeError(f"CRITICAL SAFETY VIOLATION: Target is '{current_db}', expected '{TEST_DB_NAME}'! Aborting.")
        print("  Safety Gate PASSED: Verified target is strictly 'autoinspect_test'.")

        # ---------------------------------------------------------------------
        # STEP 2: CLEAN RESET OF TEST DATABASE (ISOLATED TO autoinspect_test)
        # ---------------------------------------------------------------------
        print("\n[STEP 2] Performing clean reset of 'autoinspect_test' public schema...")
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO postgres;"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))
        conn.commit()
        print("  Test database schema reset completed.")

    # -------------------------------------------------------------------------
    # STEP 3: PRE-DATA DDL (TABLES, PRIMARY KEYS, UNIQUE CONSTRAINTS)
    # -------------------------------------------------------------------------
    print("\n[STEP 3] Applying Pre-Data DDL (Sequences, Tables, PKs, Unique Keys)...")
    with open(Path(__file__).resolve().parent.parent / "schema" / "schema_ddl.sql", "r", encoding="utf-8") as f:
        full_ddl = f.read()

    # Split into pre-data DDL and post-data DDL
    # Constraints that should run post-data loading:
    # - Foreign Keys (ensures all tables populated regardless of insertion order)
    # - inspections_vehicle_id_required NOT VALID (accommodates historical unlinked rows)
    # - Indexes (standard DBA practice for faster bulk data loading)

    pre_ddl_lines = []
    post_ddl_lines = []

    for line in full_ddl.splitlines():
        if "FOREIGN KEY" in line:
            post_ddl_lines.append(line)
        elif "inspections_vehicle_id_required" in line:
            post_ddl_lines.append(line)
        elif line.startswith("CREATE INDEX"):
            post_ddl_lines.append(line)
        else:
            pre_ddl_lines.append(line)

    pre_ddl_sql = "\n".join(pre_ddl_lines)
    post_ddl_sql = "\n".join(post_ddl_lines)

    with test_engine.connect() as conn:
        raw_conn = conn.connection
        with raw_conn.cursor() as cur:
            cur.execute(pre_ddl_sql)
        raw_conn.commit()
    print("  Pre-Data DDL applied successfully.")

    # -------------------------------------------------------------------------
    # STEP 4: RESTORE DATA FROM SQL BACKUP
    # -------------------------------------------------------------------------
    print("\n[STEP 4] Restoring data from 'autoinspect_backup_verified.sql'...")
    with open("autoinspect_backup_verified.sql", "r", encoding="utf-8") as f:
        data_sql = f.read()

    with test_engine.connect() as conn:
        raw_conn = conn.connection
        with raw_conn.cursor() as cur:
            cur.execute(data_sql)
        raw_conn.commit()
    print("  Data restoration completed: 133 total records inserted.")

    # -------------------------------------------------------------------------
    # STEP 5: APPLY POST-DATA DDL (FOREIGN KEYS, NOT VALID CHECKS, INDEXES)
    # -------------------------------------------------------------------------
    print("\n[STEP 5] Applying Post-Data DDL (Foreign Keys, NOT VALID Check Constraints, Indexes)...")
    with test_engine.connect() as conn:
        raw_conn = conn.connection
        with raw_conn.cursor() as cur:
            cur.execute(post_ddl_sql)
        raw_conn.commit()
    print("  Post-Data DDL applied successfully.")

    # -------------------------------------------------------------------------
    # STEP 6: VERIFY RESTORED RECORD COUNTS
    # -------------------------------------------------------------------------
    print("\n[STEP 6] Verifying restored record counts against backup expectations...")
    expected_counts = {
        "vehicles": 5,
        "inspections": 57,
        "damage_detections": 69,
        "detected_damages": 2,
        "users": 0,
        "profiles": 0,
        "detections": 0,
        "reports": 0,
        "regions": 0,
    }

    actual_counts = {}
    with test_engine.connect() as conn:
        for tbl, exp_cnt in expected_counts.items():
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM public.{tbl};")).scalar()
            actual_counts[tbl] = cnt
            status = "MATCH" if cnt == exp_cnt else "MISMATCH"
            print(f"  Table '{tbl:20}': Expected = {exp_cnt:2}, Restored = {cnt:2} [{status}]")
            assert cnt == exp_cnt, f"Count mismatch for '{tbl}': expected {exp_cnt}, got {cnt}"

    print("  All record counts verified with 100% precision.")

    # -------------------------------------------------------------------------
    # STEP 7: DEEP INTEGRITY CHECKS (PKS, FKS, CHECKS, ORPHANS, JSONB)
    # -------------------------------------------------------------------------
    print("\n[STEP 7] Executing deep integrity verification...")
    with test_engine.connect() as conn:
        # 7.1 Primary Key collision test
        print("  [7.1] Testing Primary Key constraint enforcement...")
        pk_collision_raised = False
        try:
            conn.execute(text("INSERT INTO public.vehicles (id, make, model, year, registration, color, image) VALUES ('1', 'BMW', 'Duplicate', 2023, 'DIFF-REG', 'White', 'img');"))
        except Exception:
            conn.rollback()
            pk_collision_raised = True
        assert pk_collision_raised, "Primary Key collision was not rejected!"
        print("    Primary Key enforcement verified: Duplicate PK correctly rejected.")

        # 7.2 Unique Key collision test
        print("  [7.2] Testing Unique Key (registration) enforcement...")
        unique_collision_raised = False
        try:
            conn.execute(text("INSERT INTO public.vehicles (id, make, model, year, registration, color, image) VALUES ('new_v', 'BMW', 'UniqueTest', 2023, 'MH-12-AB-2026', 'White', 'img');"))
        except Exception:
            conn.rollback()
            unique_collision_raised = True
        assert unique_collision_raised, "Unique registration constraint was not rejected!"
        print("    Unique Key enforcement verified: Duplicate registration 'MH-12-AB-2026' rejected.")

        # 7.3 Foreign Key: damage_detections -> inspections.inspection_id
        print("  [7.3] Auditing damage_detections foreign key integrity (UUID reference)...")
        dd_orphans = conn.execute(text("""
            SELECT COUNT(*) FROM public.damage_detections dd
            WHERE NOT EXISTS (SELECT 1 FROM public.inspections i WHERE i.inspection_id = dd.inspection_id);
        """)).scalar()
        print(f"    damage_detections orphan count: {dd_orphans}")
        assert dd_orphans == 0, f"Found {dd_orphans} orphan damage_detections!"

        # 7.4 Foreign Key: detected_damages -> inspections.id
        print("  [7.4] Auditing detected_damages foreign key integrity (numeric string reference)...")
        dam_orphans = conn.execute(text("""
            SELECT COUNT(*) FROM public.detected_damages dam
            WHERE NOT EXISTS (SELECT 1 FROM public.inspections i WHERE i.id = dam.inspection_id);
        """)).scalar()
        print(f"    detected_damages orphan count: {dam_orphans}")
        assert dam_orphans == 0, f"Found {dam_orphans} orphan detected_damages!"

        # 7.5 Foreign Key: inspections -> vehicles.id
        print("  [7.5] Auditing inspections vehicle_id foreign key integrity...")
        insp_orphans = conn.execute(text("""
            SELECT COUNT(*) FROM public.inspections i
            WHERE i.vehicle_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM public.vehicles v WHERE v.id = i.vehicle_id);
        """)).scalar()
        print(f"    inspections orphan count: {insp_orphans}")
        assert insp_orphans == 0, f"Found {insp_orphans} orphan inspections!"

        # 7.6 Foreign Key rejection test: Insert child pointing to non-existent parent
        print("  [7.6] Testing Foreign Key rejection on invalid parent ID...")
        fk_rejection_raised = False
        try:
            conn.execute(text("INSERT INTO public.damage_detections (inspection_id, class_id, class_name, confidence, box_x1, box_y1, box_x2, box_y2) VALUES ('non-existent-uuid', 1, 'Dent', 0.8, 0, 0, 10, 10);"))
        except Exception:
            conn.rollback()
            fk_rejection_raised = True
        assert fk_rejection_raised, "Foreign key allowed orphaned child insert!"
        print("    Foreign Key enforcement verified: Invalid parent ID rejected.")

        # 7.7 Check constraint: damage_detections confidence (0 <= confidence <= 1)
        print("  [7.7] Testing Check Constraint (confidence BETWEEN 0 AND 1)...")
        chk_failed = False
        try:
            conn.execute(text("INSERT INTO public.damage_detections (inspection_id, class_id, class_name, confidence, box_x1, box_y1, box_x2, box_y2) VALUES ('test-persist-check-001', 1, 'Dent', 1.8, 0, 0, 10, 10);"))
        except Exception:
            conn.rollback()
            chk_failed = True
        assert chk_failed, "Check constraint failed to reject confidence > 1!"
        print("    Check constraint verified: confidence > 1 rejected.")

        # 7.8 Post-data NOT VALID Check constraint: New inspection with NULL vehicle_id must fail
        print("  [7.8] Testing NOT VALID Check Constraint (inspections_vehicle_id_required)...")
        null_v_failed = False
        try:
            conn.execute(text("INSERT INTO public.inspections (id, vehicle_id, date, status, overall_score) VALUES ('new_test_null_v', NULL, '2026-11-08', 'completed', 80);"))
        except Exception:
            conn.rollback()
            null_v_failed = True
        assert null_v_failed, "Check constraint failed to reject new inspection with NULL vehicle_id!"
        print("    NOT VALID Check constraint verified: New inspection with NULL vehicle_id rejected.")

        # 7.9 JSONB Contents Verification
        print("  [7.9] Verifying JSONB column contents and structure...")
        jsonb_samples = conn.execute(text("SELECT id, damages, images, ai_insights FROM public.inspections WHERE damages IS NOT NULL LIMIT 5;")).fetchall()
        for s in jsonb_samples:
            assert isinstance(s[1], list) or s[1] is None
            assert isinstance(s[2], list) or s[2] is None
            assert isinstance(s[3], list) or s[3] is None
        print(f"    JSONB fields verified: Valid JSONB arrays decoded across {len(jsonb_samples)} sample rows.")

        # 7.10 Sample Read Queries
        print("  [7.10] Executing sample queries on restored data...")
        v_sample = conn.execute(text("SELECT id, make, model, registration, color, health_score FROM public.vehicles WHERE id = '1';")).fetchone()
        print(f"    Vehicle '1': {v_sample[1]} {v_sample[2]} (Reg: {v_sample[3]}, Color: {v_sample[4]}, Health: {v_sample[5]})")
        assert v_sample[1] == "BMW"
        assert v_sample[3] == "MH-12-AB-2026"

        i_sample = conn.execute(text("SELECT id, vehicle_id, overall_score, date, filename FROM public.inspections WHERE id = '4';")).fetchone()
        print(f"    Inspection '4': Vehicle: {i_sample[1]}, Score: {i_sample[2]}, Date: {i_sample[3]}, File: {i_sample[4]}")
        assert i_sample[1] == "1"
        assert i_sample[2] == 85

        # 7.11 Verify Indexes
        print("  [7.11] Auditing PostgreSQL index catalog...")
        indexes = conn.execute(text("""
            SELECT tablename, indexname FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = ANY(ARRAY['vehicles', 'inspections', 'damage_detections', 'detected_damages'])
            ORDER BY tablename, indexname;
        """)).fetchall()
        print(f"    Total indexes on core tables: {len(indexes)}")
        for idx in indexes:
            print(f"      - Table: {idx[0]:20} Index: {idx[1]}")
        assert len(indexes) >= 12, f"Expected at least 12 indexes, found {len(indexes)}"

    print("\n" + "=" * 80)
    print("RESTORATION & VERIFICATION COMPLETE: ALL INTEGRITY CHECKS PASSED (100% SUCCESS)")
    print("=" * 80)

if __name__ == "__main__":
    run_full_restoration_and_verification()
