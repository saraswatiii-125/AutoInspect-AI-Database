# AutoInspect AI — Database Security, Multi-Tenant Isolation & Access Control Specification

**AutoInspect AI — Branch 1**  
**Document Date:** November 12, 2026 (Updated with Transaction Pooler 6543 Support, Function ACL Hardening, `pg_default_acl` Advisory & PG 17 Verification)

---

## 1. Architectural Perimeter: Restricted Application Role (`autoinspect_app`) & Authorization Model

### 1.1 Current vs. Target Database Connection Boundary
- **Database Provider:** Supabase PostgreSQL (PostgreSQL 17.11 on AWS).
- **Session Pooler, Transaction Pooler (`6543`) & Direct Hosts:** Verified over Supabase Session Pooler (`aws-0-ap-northeast-1.pooler.supabase.com:5432`), **Transaction Pooler (`aws-0-ap-northeast-1.pooler.supabase.com:6543`)**, and Direct IPv6 (`db.<project_ref>.supabase.co:5432`) using SQLAlchemy ORM (`postgresql+psycopg://`).
- **Transaction Pooler Prepared-Statement Fix (`app/database.py`):** Because Supavisor Transaction Pooling (`:6543`) multiplexes backend connections per transaction, psycopg3 server-side prepared statements trigger `DuplicatePreparedStatement` errors unless disabled. [`code of UI/backend/app/database.py`](../models/app/database.py) parses `DATABASE_URL` with `make_url()` and automatically sets `connect_args={"prepare_threshold": None}` when the driver is `postgresql+psycopg` and port is `6543` (or `DB_DISABLE_PREPARED_STATEMENTS=true|1|yes`), while preserving prepared statements on Session Pooler (`5432`).
- **CRUD Rollback Hardening:** [`delete_vehicle()`](../models/app/crud/vehicle.py) and [`create_user()`](../models/app/crud/user.py) wrap `db.commit()` in `try...except Exception: db.rollback(); raise` so failed commits never poison pooled sessions.
- **Active Production State (Pending Coordinated Cutover):**
  `code of UI/backend/.env` continues using `postgres.<project_ref>` (with `rolbypassrls = true`) against `postgres` so existing backend traffic and credentials remain uninterrupted until cutover is scheduled. `.env.example` documents `?sslmode=require` and pooler port behavior without secrets.
- **Prepared Least-Privilege Application Role (`autoinspect_app`):**
  Defined in [`code of UI/backend/migrations/01_prepare_restricted_app_role.sql`](../migrations/01_prepare_restricted_app_role.sql) and fully validated end-to-end on the isolated test database `autoinspect_test`:
  - `rolsuper = false`, `rolinherit = false`, `rolcreaterole = false`, `rolcreatedb = false`, `rolcanlogin = true`, `rolreplication = false`, `rolbypassrls = false`.
  - Managed PostgreSQL note: Supabase's `postgres` role has `rolsuper = false` (`rolcreaterole = true`, `rolbypassrls = true`), so PG 17 rejects `ALTER ROLE ... NOSUPERUSER` without superuser. Omitting `NOSUPERUSER` and `NOREPLICATION` defaults both to `false`, and the migration enforces a `pg_roles` PL/pgSQL assertion block confirming all privileged flags remain `false`.
- **Single-Role Pool & Multi-Tenant Enforcement Design:**
  Because FastAPI serves all authenticated users over a shared SQLAlchemy connection pool, multi-tenant isolation (`user_id == current_user.id`) and RBAC (`customer` vs `admin`) remain **explicitly enforced at the FastAPI application layer** (`app/crud/vehicle.py`, `app/crud/inspection.py`, `app/core/dependencies.py`). Adopting `autoinspect_app` adds **defense-in-depth at the PostgreSQL layer**: it eliminates `BYPASSRLS`, blocks all DDL/TRUNCATE, blocks writes to `users` (`UPDATE`/`DELETE`) and `inspections` (`UPDATE`/`DELETE`), and denies all access to the remaining 19 tables in `public`.

### 1.2 Backend Code Privilege Audit (`code of UI/backend/app/`)
Every database access path in FastAPI was audited before designing `autoinspect_app`:

| Module / Endpoint | SQL Operations Executed | Minimum Privileges Required |
| :--- | :--- | :--- |
| `lifespan()` (`app/main.py`) | `Base.metadata.create_all(bind=engine)` inside `try/except` | Reads `pg_catalog` / `information_schema` only when schema exists; emits no DDL |
| `GET /health`, `GET /api/health` | `SELECT 1` | Database `CONNECT` only |
| `auth.py`, `crud/user.py`, `dependencies.py` | Lookup by email/id; create new customer account | `SELECT, INSERT` on `public.users`; `USAGE, SELECT` on `public.users_id_seq` |
| `vehicles.py`, `crud/vehicle.py` | Vehicle CRUD + cascade delete (`passive_deletes=True`) | `SELECT, INSERT, UPDATE, DELETE` on `public.vehicles`; `SELECT` on `public.inspections` |
| `inspections.py`, `crud/inspection.py` | Read/create inspections + sync vehicle `health_score` & `latest_inspection_date` | `SELECT, INSERT` on `public.inspections`; `SELECT, UPDATE` on `public.vehicles` |
| Remaining 19 `public` tables (`profiles`, `damage_detections`, `detected_damages`, `detections`, `reports`, `regions`, `id`, 12 `*_20261101` backup tables) | Never queried by FastAPI runtime | **ZERO GRANTS** (`ON DELETE CASCADE` triggers execute as table owner `postgres`) |

---

## 2. Multi-Tenant Role-Based Access Control (RBAC)

The system defines two strict roles backed by the `users` database table:

| Role | Vehicle Access Permissions | Inspection Access Permissions | Deletion Rights |
| :--- | :--- | :--- | :--- |
| **`customer`** | Restricted strictly to vehicles where `user_id == current_user.id` | Restricted strictly to inspections where `user_id == current_user.id` | Can delete only their own vehicles |
| **`admin`** | Unrestricted fleet access: all user vehicles AND legacy unowned vehicles (`user_id IS NULL`) | Unrestricted access: all inspections across all vehicles AND unassigned inspections | Can delete any vehicle or inspection |
| **Unknown / Invalid** | Rejected immediately with **HTTP 403 Forbidden** | Rejected immediately with **HTTP 403 Forbidden** | Rejected |

### Anti-Enumeration Protection
When a customer attempts to read, edit, or delete a vehicle or inspection owned by another customer, the API returns **HTTP 404 Not Found** (not HTTP 403 Forbidden). This completely prevents malicious actors from probing or enumerating valid vehicle registrations or inspection IDs belonging to other users.

---

## 3. Empirical Multi-Tenant Isolation Proof

The isolation boundaries were verified in `code of UI/backend/test_database_persistence_isolation.py` against live Supabase PostgreSQL:

```
[SETUP] Created test users: Customer A (1001), Customer B (1002), Admin (1003)
--- PHASE 5: CUSTOMER VS CUSTOMER ISOLATION & ADMIN ACCESS ---
  [5.1] List isolation verified: Customer B returned 0 vehicles, excluding Customer A's vehicle.
  [5.2] Read isolation verified: Customer B read of Customer A's vehicle rejected with 404.
  [5.3] Update isolation verified: Customer B update of Customer A's vehicle rejected with 404.
  [5.4] Delete isolation verified: Customer B delete of Customer A's vehicle rejected with 404.
  [5.5] Inspection read isolation verified: Customer B read of Customer A's inspection rejected with 404.
  [5.6] Inspection list isolation verified: Customer B returned 0 inspections, excluding Customer A's inspection.
  [5.7] Admin fleet access verified: Admin successfully accessed Customer A's vehicle and inspection.
```

### Verified Test Assertions:
1. **List Filtering:** Customer B's `GET /api/vehicles` query automatically translates to:
   `SELECT * FROM vehicles WHERE user_id = 1002;`
   Customer A's vehicle (user_id = 1001) is strictly excluded from query results.
2. **Read Isolation:** Customer B's `GET /api/vehicles/{id_of_a}` translates to:
   `SELECT * FROM vehicles WHERE id = :id AND user_id = 1002;`
   Returns 0 rows, triggering `HTTPException(status_code=404, detail="Vehicle not found")`.
3. **Cross-Tenant Mutation Prevention:** Customer B cannot update or delete Customer A's vehicle; returns 404 without altering any database rows.
4. **Child Inspection Isolation:** Customer B cannot read or list Customer A's inspection reports.
5. **Admin Fleet Management:** Admin users can view the full fleet and manage unowned legacy records.

---

## 4. PostgreSQL Role Privileges, Grants & Scoped RLS Matrix

All 22 tables in `public` have Row Level Security (`relrowsecurity = true`) enabled, and **zero** table or sequence privileges are granted to `PUBLIC` or `anon`.

| Table / Sequence | `PUBLIC` / `anon` | `authenticated` (Supabase Auth, RLS) | `autoinspect_app` (`NOBYPASSRLS`, App Pool Role) | `postgres` (Admin / Owner) | Security Guarantee |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `public.users` | **NONE** | **NONE** | `SELECT, INSERT` (RLS scoped `TO autoinspect_app`) | OWNER / ALL | Direct client PostgREST blocked; backend cannot `UPDATE`/`DELETE` accounts or tamper roles |
| `public.users_id_seq` | **NONE** | `USAGE, SELECT, UPDATE` | `USAGE, SELECT` | OWNER / ALL | Permits registration ID allocation without sequence reset privileges |
| `public.vehicles` | **NONE** | `SELECT, INSERT, UPDATE, DELETE` | `SELECT, INSERT, UPDATE, DELETE` (RLS scoped `TO autoinspect_app`) | OWNER / ALL | Supports fleet CRUD while blocking DDL/TRUNCATE |
| `public.inspections` | **NONE** | `SELECT, INSERT, UPDATE, DELETE` | `SELECT, INSERT` (RLS scoped `TO autoinspect_app`) | OWNER / ALL | Immutable inspection history from app pool; FK `ON DELETE CASCADE` from `vehicles` runs as owner `postgres` |
| `public.profiles` | **NONE** | `SELECT, UPDATE` | **NONE** | OWNER / ALL | Zero runtime access needed by FastAPI |
| `public.damage_detections`, `detected_damages`, `detections` | **NONE** | `SELECT, INSERT, UPDATE, DELETE` | **NONE** | OWNER / ALL | Unreferenced by runtime pool; cascading cleanup handled safely by PostgreSQL FK triggers as owner |
| `public.reports`, `regions`, `id`, & 12 `*_20261101` backup tables | **NONE** | **NONE** | **NONE** | OWNER / ALL | Strictly isolated from both clients and the FastAPI application role |

### Scoped RLS Interaction (`NOBYPASSRLS`) & Function ACL Hardening
Because `autoinspect_app` has `rolbypassrls = false` and all `public` tables enforce RLS:
- Queries without an explicit policy for `autoinspect_app` fail closed by default (empirically proven: `SELECT COUNT(*) FROM public.vehicles` returned `0` out of 5 rows and `INSERT INTO public.users` raised `InsufficientPrivilege: new row violates row-level security policy` prior to policy creation).
- [`01_prepare_restricted_app_role.sql`](../migrations/01_prepare_restricted_app_role.sql) attaches permissive RLS policies strictly `TO autoinspect_app` on only `users` (`SELECT, INSERT`), `vehicles` (`SELECT, INSERT, UPDATE, DELETE`), and `inspections` (`SELECT, INSERT`) — keeping `anon` and `authenticated` completely unaffected.
- **Function & Schema Hardening:** The migration also revokes `CREATE ON SCHEMA public FROM PUBLIC` (inside an exception-safe `DO` block for non-owner execution) and runs a `pg_catalog.pg_get_function_identity_arguments(p.oid)` loop revoking `ALL ON FUNCTION ... FROM PUBLIC` and `autoinspect_app` on all non-extension `public` functions (`handle_new_user()`, `handle_user_email_change()`, `is_admin()`, `protect_profile_fields()`) while leaving existing `service_role` / `authenticated` ACLs untouched.

> [!WARNING]
> **Production Risk Advisory — `pg_default_acl` Auto-Grants on New Objects:**
> Inspecting `pg_catalog.pg_default_acl` on production `postgres` shows Supabase's default privilege rules automatically grant `ALL` on newly created tables, sequences, and functions in schema `public` (created by `postgres` or `supabase_admin`) to `anon`, `authenticated`, and `service_role`. Whenever adding new tables, sequences, or functions in `public`, operators must explicitly run `REVOKE ALL ... FROM PUBLIC, anon` and enable RLS in the same migration.

---

## 5. Empirically Verified Restricted Role End-to-End Suite (`autoinspect_test`)

[`test_restricted_role_live.py`](../tests/test_restricted_role_live.py) executed an end-to-end verification strictly against `autoinspect_test` (**production database `postgres` and `backend/.env` remained untouched**, verified with `0` grants for `autoinspect_app` on `postgres`):

1. **All 3 Connection Paths + Concurrency Verified:** Connected as `autoinspect_app` to `autoinspect_test` over Supabase **Session Pooler (`:5432`)**, **Transaction Pooler (`:6543`) with 8 concurrent `ThreadPoolExecutor` workers on `app.database.engine`**, and **Direct IPv6 (`:5432`)**.
2. **FastAPI HTTP `TestClient` Lifecycle Verified over Transaction Pooler (`6543`):** Executed `lifespan` startup, `/health`, `/api/auth/register`, `/api/auth/login`, `/api/auth/me`, `/api/vehicles` CRUD, `/api/inspections` creation/read, cross-tenant `404` isolation, admin fleet visibility, and multi-level `ON DELETE CASCADE` (`vehicles -> inspections -> damage_detections` with zero grants to `autoinspect_app` on `damage_detections`).
3. **17 Negative Least-Privilege & Production Isolation Assertions Passed:** Confirmed PostgreSQL rejects `CREATE TABLE`, `DROP TABLE`, `ALTER TABLE`, `TRUNCATE`, `CREATE FUNCTION`, `UPDATE`/`DELETE` on `users` and `inspections`, any `SELECT` on `profiles`, `damage_detections`, `detected_damages`, and `vehicles_backup_20261101`, `EXECUTE` on all 4 `public` functions (plus `pg_proc.proacl` audit confirming 0 `PUBLIC`/`autoinspect_app` grants), and rejects connecting to production database `postgres` over Session Pooler.

---

## 6. Defense-in-Depth & Production Cutover Coordination

1. **Authentication & Crypto:** Stateless HS256 JWT tokens (`JWT_SECRET_KEY` $\ge 32$ chars) and Argon2id password hashing (`m=65536, t=3, p=4`) with constant-time dummy hash verification.
2. **Coordinated Production Cutover Runbook (Remaining Operational Step):**
   1. Generate a high-entropy 256-bit password in a secret manager for `autoinspect_app` (never commit secrets to git or `.env.example`).
   2. Connect as `postgres` to database **`postgres`** and execute [`01_prepare_restricted_app_role.sql`](../migrations/01_prepare_restricted_app_role.sql) (rotating `PASSWORD` in Part A and applying Parts B & C).
   3. Update `DATABASE_URL` in `code of UI/backend/.env` to `postgresql+psycopg://autoinspect_app.<project_ref>:<PASSWORD>@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres?sslmode=require` (or `:6543` for Transaction Pooler).
   4. Restart the FastAPI service and run `GET /health` + smoke auth/vehicle checks.
   5. **Rollback:** Restore original `postgres.<project_ref>` connection string in `.env` and restart FastAPI.
3. **Remaining Architectural Limitations:**
   - FastAPI connects through a single application role (`autoinspect_app`); row-level multi-tenant ownership (`user_id == current_user.id`) relies on audited FastAPI ORM scoping rather than per-request `SET LOCAL` PostgreSQL user session variables (can be layered in Phase 2).
   - Existing backend `code of UI/backend/.env` still points to `postgres.<project_ref>` until coordinated cutover is performed by the operator.
   - Supabase `pg_default_acl` in `public` requires explicit `REVOKE` + RLS when creating any future schema objects.
