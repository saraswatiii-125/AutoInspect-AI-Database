"""
AutoInspect AI - Full End-to-End Restricted Role Test Suite (`autoinspect_app` on `autoinspect_test`).

Executes against the isolated test database `autoinspect_test` ONLY:
1. Applies `migrations/01_prepare_restricted_app_role.sql` safely onto `autoinspect_test`
   (substituting the target password strictly in process memory — never written to disk).
2. Verifies ALL THREE Supabase connection paths as `autoinspect_app`:
   - Session Pooler (`aws-0-*.pooler.supabase.com:5432`)
   - Transaction Pooler (`aws-0-*.pooler.supabase.com:6543`) with concurrent SQLAlchemy
     connections proving zero `DuplicatePreparedStatement` errors via `prepare_threshold=None`
   - Direct IPv6 (`db.<ref>.supabase.co:5432`)
3. Proves FastAPI app startup (`lifespan`), `/health`, `/api/health`, `/api/auth/register`,
   `/api/auth/login`, `/api/auth/me`, `/api/vehicles`, `/api/inspections`, customer/admin
   isolation, rollback/error recovery, AND multi-level `ON DELETE CASCADE`
   (`vehicles -> inspections -> damage_detections`) via HTTP `TestClient` as `autoinspect_app`.
4. Verifies strict least-privilege denials (DDL on tables/functions, TRUNCATE, unauthorized
   table reads/writes, `PUBLIC` & `autoinspect_app` function EXECUTE denials, and
   cross-database production `postgres` isolation).
5. Restores `autoinspect_test` back to clean restored baseline and verifies production `postgres` untouched.
"""

import sys as _sys
from pathlib import Path as _Path
_MODELS_DIR = _Path(__file__).resolve().parent.parent / 'models'
if str(_MODELS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_MODELS_DIR))

import os
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote_plus

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import settings

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_SQL_PATH = REPO_ROOT / "migrations" / "01_prepare_restricted_app_role.sql"
TEST_DB_NAME = "autoinspect_test"
ROLE_NAME = "autoinspect_app"

PROD_DATABASE_URL = settings.DATABASE_URL
parsed = make_url(PROD_DATABASE_URL)
POOLER_HOST = parsed.host
PORT = parsed.port or 5432
raw_user = parsed.username or "postgres"
PROJECT_REF = raw_user.split(".", 1)[1] if "." in raw_user else ""
DIRECT_HOST = f"db.{PROJECT_REF}.supabase.co" if PROJECT_REF else POOLER_HOST

admin_prod_engine = create_engine(PROD_DATABASE_URL)
admin_test_url = parsed.set(database=TEST_DB_NAME)
admin_test_engine = create_engine(admin_test_url)

# Ephemeral strong secret strictly in process memory
ephemeral_pw = secrets.token_urlsafe(32)
encoded_pw = quote_plus(ephemeral_pw)
pooler_user = f"{ROLE_NAME}.{PROJECT_REF}" if PROJECT_REF else ROLE_NAME

APP_TEST_POOLER_URL = f"postgresql+psycopg://{pooler_user}:{encoded_pw}@{POOLER_HOST}:{PORT}/{TEST_DB_NAME}?sslmode=require"
APP_TEST_TX_POOLER_URL = f"postgresql+psycopg://{pooler_user}:{encoded_pw}@{POOLER_HOST}:6543/{TEST_DB_NAME}?sslmode=require"
APP_TEST_DIRECT_URL = f"postgresql+psycopg://{ROLE_NAME}:{encoded_pw}@{DIRECT_HOST}:{PORT}/{TEST_DB_NAME}?sslmode=require"
APP_PROD_POOLER_URL = f"postgresql+psycopg://{pooler_user}:{encoded_pw}@{POOLER_HOST}:{PORT}/postgres?sslmode=require"

# Point FastAPI's upcoming import of `app.database` strictly to autoinspect_test via port 6543
# Transaction Pooler as `autoinspect_app`! That exercises Transaction Pooler + prepare_threshold=None
# end-to-end across FastAPI lifespan and every endpoint.
os.environ["DATABASE_URL"] = APP_TEST_TX_POOLER_URL
os.environ["RATE_LIMIT_ENABLED"] = "false"

# Import FastAPI app AFTER setting process-local test DATABASE_URL
from app.main import app  # noqa: E402
from app.database import engine as app_engine  # noqa: E402

assert app_engine.url.database == TEST_DB_NAME and (app_engine.url.username or "").startswith(ROLE_NAME), (
    f"Safety check failed: app_engine targets {app_engine.url.database} as {app_engine.url.username}"
)


def run_suite() -> None:
    print("=" * 80)
    print("AUTOINSPECT AI - FULL E2E TEST SUITE ON RESTRICTED ROLE (`autoinspect_app`)")
    print("Target Database: autoinspect_test ONLY (Production untouched)")
    print("=" * 80)

    # 1. Apply migration SQL file to `autoinspect_test` ONLY
    print("\n[1/5] Applying 01_prepare_restricted_app_role.sql onto 'autoinspect_test'...")
    migration_sql = MIGRATION_SQL_PATH.read_text(encoding="utf-8")
    escaped_pw = ephemeral_pw.replace("'", "''")
    rendered_sql = migration_sql.replace(
        "<REPLACE_WITH_STRONG_256BIT_PASSWORD>",
        escaped_pw,
    )
    with admin_test_engine.connect() as conn:
        assert conn.execute(text("SELECT current_database();")).scalar() == TEST_DB_NAME
        raw_conn = conn.connection
        try:
            with raw_conn.cursor() as cur:
                cur.execute(rendered_sql)
            raw_conn.commit()
        except Exception as exc:
            raw_conn.rollback()
            sanitized = str(exc)
            for secret_val in (escaped_pw, ephemeral_pw, encoded_pw):
                if secret_val:
                    sanitized = sanitized.replace(secret_val, "***REDACTED***")
            raise RuntimeError(f"Migration SQL execution failed: {type(exc).__name__}: {sanitized}") from None
    print("  PASSED: Restricted role, zero-PUBLIC function hardening, & minimal grants/policies applied.")

    # 2. Verify Session Pooler (5432), Transaction Pooler (6543 concurrent), & Direct IPv6 (5432)
    print("\n[2/5] Verifying Session Pooler (5432), Transaction Pooler (6543), & Direct IPv6 connections...")
    sess_eng = create_engine(APP_TEST_POOLER_URL)
    with sess_eng.connect() as conn:
        assert conn.execute(text("SELECT current_user, current_database();")).fetchone() == (ROLE_NAME, TEST_DB_NAME)
    sess_eng.dispose()

    # Exercise concurrent multi-connection parameterized queries on port 6543 via app_engine
    # (proving connect_args={"prepare_threshold": None} prevents DuplicatePreparedStatement)
    def _tx_pooler_worker(idx: int) -> int:
        with app_engine.connect() as tconn:
            for round_i in range(3):
                val = tconn.execute(
                    text("SELECT COUNT(*) FROM public.vehicles WHERE year >= :y;"),
                    {"y": 2000 + round_i},
                ).scalar()
                assert val is not None
        return idx

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_tx_pooler_worker, range(8)))
    assert len(results) == 8

    direct_eng = create_engine(APP_TEST_DIRECT_URL)
    with direct_eng.connect() as dconn:
        assert dconn.execute(text("SELECT current_user, current_database();")).fetchone() == (ROLE_NAME, TEST_DB_NAME)
    direct_eng.dispose()
    print("  PASSED: Connected as ('autoinspect_app', 'autoinspect_test') across Session (5432), Concurrent Tx (6543), & Direct IPv6.")

    # 3. Full HTTP FastAPI TestClient Lifecycle (`lifespan` + auth + CRUD + RBAC + error recovery + cascade)
    print("\n[3/5] Running FastAPI HTTP TestClient end-to-end checks on Transaction Pooler (6543) as 'autoinspect_app'...")
    run_tag = uuid.uuid4().hex[:8]
    email_a = f"e2e_a_{run_tag}@example.com"
    email_b = f"e2e_b_{run_tag}@example.com"
    admin_email = f"e2e_admin_{run_tag}@example.com"
    pw_user = "StrongPass!2026"
    v_id = f"tmp_e2e_v_{run_tag}"
    reg_a = f"TMP-E2E-{run_tag.upper()}"
    i_id = f"tmp_e2e_i_{run_tag}"
    i_uuid = str(uuid.uuid4())

    with TestClient(app) as client:
        # 3.1 Lifespan + health check
        r_health = client.get("/health")
        assert r_health.status_code == 200 and r_health.json()["status"] == "ok"

        # 3.2 Register two customers via HTTP + verify duplicate 409 rollback recovery
        r_reg_a = client.post("/api/auth/register", json={"email": email_a, "password": pw_user})
        r_reg_b = client.post("/api/auth/register", json={"email": email_b, "password": pw_user})
        assert r_reg_a.status_code == 201 and r_reg_b.status_code == 201
        r_reg_dup = client.post("/api/auth/register", json={"email": email_a, "password": pw_user})
        assert r_reg_dup.status_code == 409

        # 3.3 Login Customer A & B, verify /api/auth/me
        tok_a = client.post("/api/auth/login", json={"email": email_a, "password": pw_user}).json()["accessToken"]
        tok_b = client.post("/api/auth/login", json={"email": email_b, "password": pw_user}).json()["accessToken"]
        hdr_a = {"Authorization": f"Bearer {tok_a}"}
        hdr_b = {"Authorization": f"Bearer {tok_b}"}
        assert client.get("/api/auth/me", headers=hdr_a).json()["email"] == email_a

        # 3.4 Customer A vehicle create, duplicate recovery, list, read, update
        r_vc = client.post(
            "/api/vehicles",
            headers=hdr_a,
            json={
                "id": v_id,
                "make": "BMW",
                "model": "M5",
                "year": 2025,
                "registration": reg_a,
                "color": "Frozen Black",
                "image": "https://example.com/m5.jpg",
            },
        )
        assert r_vc.status_code == 201, r_vc.text
        assert len(client.get("/api/vehicles", headers=hdr_a).json()) == 1
        assert len(client.get("/api/vehicles", headers=hdr_b).json()) == 0
        assert client.get(f"/api/vehicles/{v_id}", headers=hdr_b).status_code == 404

        r_vu = client.put(f"/api/vehicles/{v_id}", headers=hdr_a, json={"color": "Marina Bay Blue"})
        assert r_vu.status_code == 200 and r_vu.json()["color"] == "Marina Bay Blue"

        # 3.5 Inspection create & read + cross-tenant 404
        r_ic = client.post(
            "/api/inspections",
            headers=hdr_a,
            json={
                "id": i_id,
                "vehicleId": v_id,
                "overallScore": 88,
                "damages": [],
                "images": [],
                "aiInsights": ["Clean body"],
            },
        )
        assert r_ic.status_code == 201, r_ic.text
        assert client.get(f"/api/vehicles/{v_id}", headers=hdr_a).json()["healthScore"] == 88
        assert client.get(f"/api/inspections/{i_id}", headers=hdr_b).status_code == 404

        # 3.6 Admin role test (create admin directly via admin_test_engine, login via HTTP, verify full baseline fleet visible)
        from app.core.security import hash_password
        with admin_test_engine.connect() as aconn:
            aconn.execute(
                text("INSERT INTO public.users (email, hashed_password, role) VALUES (:e, :p, 'admin');"),
                {"e": admin_email, "p": hash_password(pw_user)},
            )
            # Also attach inspection_id UUID & child row in damage_detections to prove deep CASCADE delete!
            aconn.execute(
                text("UPDATE public.inspections SET inspection_id = :iu WHERE id = :iid;"),
                {"iu": i_uuid, "iid": i_id},
            )
            aconn.execute(
                text("INSERT INTO public.damage_detections (inspection_id, class_id, class_name, confidence, box_x1, box_y1, box_x2, box_y2) VALUES (:iu, 1, 'Scratch', 0.9100, 10, 10, 50, 50);"),
                {"iu": i_uuid},
            )
            aconn.commit()

        tok_adm = client.post("/api/auth/login", json={"email": admin_email, "password": pw_user}).json()["accessToken"]
        hdr_adm = {"Authorization": f"Bearer {tok_adm}"}
        assert len(client.get("/api/vehicles", headers=hdr_adm).json()) == 6  # 5 baseline + 1 temp
        assert len(client.get("/api/inspections", headers=hdr_adm).json()) == 58  # 57 baseline + 1 temp

        # 3.7 Delete vehicle as `autoinspect_app` -> cascades to inspection AND damage_detections (with 0 grant on damage_detections!)
        r_del = client.delete(f"/api/vehicles/{v_id}", headers=hdr_a)
        assert r_del.status_code == 200 and r_del.json()["success"] is True

        with admin_test_engine.connect() as aconn:
            assert aconn.execute(text("SELECT COUNT(*) FROM public.inspections WHERE id = :iid;"), {"iid": i_id}).scalar() == 0
            assert aconn.execute(text("SELECT COUNT(*) FROM public.damage_detections WHERE inspection_id = :iu;"), {"iu": i_uuid}).scalar() == 0

    print("  PASSED: Full HTTP TestClient suite (6543 Tx Pooler, lifespan, auth, isolation, admin fleet, deep CASCADE delete) succeeded!")

    # 4. Negative Least-Privilege (Tables, DDL, Functions) & Production Isolation Checks
    print("\n[4/5] Verifying strict negative privilege boundaries...")
    with app_engine.connect() as conn:
        negative_stmts = [
            "CREATE TABLE public.bad_ddl (x int);",
            "CREATE FUNCTION public.bad_fn() RETURNS int LANGUAGE sql AS 'SELECT 1';",
            "DROP TABLE public.vehicles;",
            "ALTER TABLE public.vehicles ADD COLUMN bad text;",
            "TRUNCATE TABLE public.vehicles;",
            f"UPDATE public.users SET role = 'admin' WHERE email = '{email_a}';",
            f"DELETE FROM public.users WHERE email = '{email_a}';",
            "UPDATE public.inspections SET overall_score = 0 WHERE id = '4';",
            "DELETE FROM public.inspections WHERE id = '4';",
            "SELECT COUNT(*) FROM public.profiles;",
            "SELECT COUNT(*) FROM public.damage_detections;",
            "SELECT COUNT(*) FROM public.detected_damages;",
            "SELECT COUNT(*) FROM public.vehicles_backup_20261101;",
            "SELECT public.is_admin();",
            "SELECT public.handle_new_user();",
            "SELECT public.handle_user_email_change();",
            "SELECT public.protect_profile_fields();",
        ]
        for stmt in negative_stmts:
            denied = False
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                conn.rollback()
                denied = True
            assert denied, f"Least-privilege check failed for: {stmt}"

        # Assert PUBLIC & autoinspect_app hold 0 EXECUTE privileges on all public user-defined functions
        fn_exec = conn.execute(
            text("""
                SELECT p.proname
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public'
                  AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e')
                  AND (
                      pg_catalog.has_function_privilege('public', p.oid, 'EXECUTE')
                      OR pg_catalog.has_function_privilege('autoinspect_app', p.oid, 'EXECUTE')
                  );
            """)
        ).fetchall()
        assert not fn_exec, f"Unexpected function EXECUTE privilege for PUBLIC/autoinspect_app: {fn_exec}"

    app_prod_eng = create_engine(APP_PROD_POOLER_URL)
    prod_denied = False
    try:
        with app_prod_eng.connect() as pconn:
            pconn.execute(text("SELECT COUNT(*) FROM public.vehicles;"))
    except Exception:
        prod_denied = True
    finally:
        app_prod_eng.dispose()
    assert prod_denied, "CRITICAL: autoinspect_app could access production DB 'postgres'!"
    print(f"  PASSED: All {len(negative_stmts)} negative privilege assertions + function EXECUTE denials + production DB isolation verified!")

    app_engine.dispose()

    # 5. Cleanup temp users in autoinspect_test & confirm production untouched
    print("\n[5/5] Restoring 'autoinspect_test' baseline & confirming production DB untouched...")
    with admin_test_engine.connect() as conn:
        conn.execute(
            text("DELETE FROM public.users WHERE email = ANY(:emails);"),
            {"emails": [email_a, email_b, admin_email]},
        )
        conn.execute(text("SELECT pg_catalog.setval('public.\"users_id_seq\"', 1, false);"))
        conn.commit()
        assert conn.execute(text("SELECT COUNT(*) FROM public.vehicles;")).scalar() == 5
        assert conn.execute(text("SELECT COUNT(*) FROM public.inspections;")).scalar() == 57
        assert conn.execute(text("SELECT COUNT(*) FROM public.users;")).scalar() == 0

    with admin_prod_engine.connect() as pconn:
        assert pconn.execute(text("SELECT COUNT(*) FROM public.vehicles;")).scalar() == 5
        assert pconn.execute(text("SELECT COUNT(*) FROM public.inspections;")).scalar() == 57
        assert pconn.execute(text("SELECT COUNT(*) FROM public.users;")).scalar() == 0
        assert pconn.execute(text("SELECT COUNT(*) FROM information_schema.role_table_grants WHERE grantee = :r;"), {"r": ROLE_NAME}).scalar() == 0

    print("  PASSED: autoinspect_test clean (5 vehicles, 57 inspections, 0 users) & production DB untouched (0 grants).")
    print("\n" + "=" * 80)
    print("END-TO-END RESTRICTED ROLE SUITE: 100% PASS")
    print("=" * 80)


if __name__ == "__main__":
    run_suite()
