# AutoInspect AI — PostgreSQL Database Architecture, Security, Testing & Recovery (Branch 1)

This repository contains the complete database engineering implementation, schema architecture, SQLAlchemy ORM persistence layer, least-privilege PostgreSQL role hardening, automated test suites, ER diagrams, and backup/recovery automation for **AutoInspect AI — Branch 1**.

> [!IMPORTANT]
> **Public Repository Security & Scope Notice**
> - All credentials, `.env` files, production connection strings, customer records, and raw database dump/data export files (`*.dump`, `autoinspect_complete_backup.sql`, `autoinspect_backup_verified.*`) are strictly omitted from this repository.
> - Database backup and restoration scripts in this repository target the **`public` schema only** (`22` tables, `267` active columns, `7` sequences, `23` indexes) and do **not** represent a full Supabase project backup (Supabase-managed `auth`, `storage`, `realtime`, `vault` schemas and cluster roles require Supabase platform PITR/snapshots).

---

## Repository Structure

```text
AutoInspect-AI-Database/
├── README.md                                  # Complete academic & engineering overview
├── requirements.txt                           # SQLAlchemy, psycopg 3, FastAPI, Pydantic, Argon2id & PyJWT deps
├── schema/
│   ├── schema_ddl.sql                         # Core 9-table PostgreSQL DDL (tables, PKs, UKs, CHECK, FKs, indexes)
│   └── complete_backup_manifest.json          # Machine-readable catalog manifest (22 tables, 7 seqs, 25 constraints, 23 indexes)
├── migrations/
│   └── 01_prepare_restricted_app_role.sql     # Least-privilege role `autoinspect_app` (NOBYPASSRLS, grants, function ACLs, scoped RLS)
├── models/                                    # SQLAlchemy ORM models, pooling, CRUD persistence, Pydantic contracts & RBAC
│   └── app/
│       ├── config.py                          # PostgreSQL URL enforcement (zero SQLite fallback) & JWT settings
│       ├── database.py                        # SQLAlchemy Engine + Supavisor :6543 prepared-statement auto-disable
│       ├── main.py                            # Health probe, ASGI security headers, host whitelist & routers
│       ├── models/                            # UserModel, VehicleModel, InspectionModel ORM definitions
│       ├── crud/                              # Transactional CRUD with tenant ownership scoping & rollback safety
│       ├── schemas/                           # Strict Pydantic v2 contracts (`extra="forbid"`, camelCase aliases)
│       ├── core/                              # Argon2id hashing, HS256 JWT verification, rate limiting & dependencies
│       └── routers/                           # Customer/admin isolated API endpoints
├── tests/                                     # Live PostgreSQL isolation, CRUD, restricted-role E2E & security suites
│   ├── test_database_persistence_isolation.py # Multi-tenant isolation, JSONB integrity & cascade delete suite
│   ├── test_crud_live.py                      # 8-case live PostgreSQL CRUD lifecycle + baseline safety gates
│   ├── test_restricted_role_live.py           # `autoinspect_app` E2E (Session 5432, 8-thread Tx 6543, Direct IPv6, 17 denials)
│   ├── test_backend.py                        # 10 backend/PostgreSQL regression & cascade tests
│   └── test_security_hardening.py             # 13 security middleware, JWT, rate-limit & schema bound tests
├── backup-recovery/                           # PostgreSQL backup, DDL extraction, seeding & parity restore scripts
│   ├── generate_complete_backup.py            # Read-only pg_catalog logical SQL exporter + manifest generator
│   ├── run_complete_restore_test.py           # Atomic single-pass restore & 100% object/ACL parity verifier
│   ├── generate_backup.py                     # Legacy 9-table SQL+JSON exporter
│   ├── run_restore_test.py                    # Two-phase DDL + data restore verifier
│   ├── extract_schema_ddl.py                  # Core PostgreSQL DDL extractor
│   └── seed.py                                # Idempotent baseline seeder
├── diagrams/
│   ├── DATABASE_ER_DIAGRAM.md                 # Mermaid Entity-Relationship specification & cascade documentation
│   └── autoinspect_er_diagram.mmd             # Standalone Mermaid ER source diagram
└── documentation/                             # Detailed schema, index, security, restore & verification reports
```

---

## 1. Project Overview & Database Technology

- **Database Engine:** PostgreSQL 17.11 (hosted on Supabase AWS).
- **ORM & Driver:** SQLAlchemy 2.0+ with **psycopg 3** (`postgresql+psycopg://`).
- **Connection Modes Supported & Verified:**
  - Supabase Session Pooler (`:5432`, server-side prepared statements enabled).
  - Supabase Transaction Pooler / Supavisor (`:6543`, [`models/app/database.py`](models/app/database.py) parses `DATABASE_URL` via `make_url()` and automatically passes `connect_args={"prepare_threshold": None}` to eliminate `DuplicatePreparedStatement` errors).
  - Direct PostgreSQL IPv6 (`:5432`).
- **Authentication & Cryptography:** Argon2id (`time_cost=3, memory_cost=65536, parallelism=4`) + HS256 JWT (`pyjwt`) + `users` PostgreSQL table (`public.users`).

---

## 2. Database Architecture, Tables & Relationships

The live `public` schema comprises **22 tables** (**267 active columns**, `393` baseline rows), grouped into **10 core/schema tables** and **12 historical `2026-11-01` backup/checkpoint tables**:

| Core Table | Primary Key | Foreign Keys & Delete Actions | Purpose |
| :--- | :--- | :--- | :--- |
| `users` | `id` (`integer`, `users_id_seq`) | — | Custom FastAPI auth accounts (`email` unique, `hashed_password`, `role`) |
| `profiles` | `id` (`uuid`) | `id -> auth.users(id) ON DELETE CASCADE` | Legacy Supabase Auth profile mirror + `protect_profile_fields_trigger` |
| `vehicles` | `id` (`text`) | `user_id -> users.id ON DELETE CASCADE`<br>`owner_id -> profiles.id ON DELETE SET NULL` | Fleet & customer vehicles (`registration` unique, partial unique `code`) |
| `inspections` | `id` (`text`), unique `inspection_id` (`text`) | `vehicle_id -> vehicles.id ON DELETE CASCADE`<br>`user_id -> users.id ON DELETE CASCADE` | AI vehicle inspections with `JSONB` `damages`, `images`, `ai_insights` |
| `damage_detections` | `id` (`uuid`, `gen_random_uuid()`) | `inspection_id -> inspections.inspection_id ON DELETE CASCADE` | Normalized YOLO bounding boxes (`confidence`, `box_x1..y2`) |
| `detected_damages` | `id` (`integer`, `detected_damages_id_seq`) | `inspection_id -> inspections.id ON DELETE CASCADE` | Secondary/legacy damage detections |
| `detections` | `id` (`integer`, `detections_id_seq`) | `inspection_id -> inspections.id ON DELETE CASCADE` | Vision bounding-box detection records |
| `reports` | `id` (`integer`, `reports_id_seq`) | `inspection_id -> inspections.id ON DELETE CASCADE` | Inspection PDF report metadata |
| `regions` | `id` (`jsonb`) | — | Legacy region payload table |
| `id` | `id` (`bigint IDENTITY`, `id_id_seq`) | — | Auxiliary identity/timestamp table |

Detailed column tables and ER diagrams are available in [`diagrams/DATABASE_ER_DIAGRAM.md`](diagrams/DATABASE_ER_DIAGRAM.md), [`documentation/DATABASE_SCHEMA.md`](documentation/DATABASE_SCHEMA.md), and [`documentation/DATABASE_RELATIONSHIPS.md`](documentation/DATABASE_RELATIONSHIPS.md).

---

## 3. Constraints, Indexes & Data Persistence

- **25 Production Constraints (`24` in `public` + `1` external FK to `auth.users`):**
  - `13` Primary Key & Unique constraints (`users_pkey`, `users_email_key`, `vehicles_pkey`, `vehicles_registration_key`, `inspections_pkey`, `inspections_inspection_id_key`, etc.).
  - `3` Check constraints (`damage_detections_confidence_check` `[0,1]`, `profiles_role_check`, and `inspections_vehicle_id_required` **`CHECK (vehicle_id IS NOT NULL) NOT VALID`** preserving 8 historical unlinked rows while requiring `vehicle_id` on all new inserts).
  - `8` Intra-`public` Foreign Keys (`ON DELETE CASCADE` on inspection/damage hierarchies; `ON DELETE SET NULL` on legacy `vehicles.owner_id`).
- **23 Active PostgreSQL Indexes (`pg_indexes`):**
  - `13` constraint-backing PK/UK indexes + `10` standalone indexes covering every foreign key (`idx_vehicles_user_id`, `idx_vehicles_owner_id`, `idx_inspections_vehicle_id`, `idx_inspections_user_id`, `idx_damage_detections_inspection_id`, `idx_detected_damages_inspection_id`, `idx_detections_inspection_id`, `idx_reports_inspection_id`), timestamp sorting (`idx_inspections_created_at DESC`), and partial uniqueness (`idx_vehicles_code WHERE code IS NOT NULL`). See [`documentation/DATABASE_INDEX_AUDIT.md`](documentation/DATABASE_INDEX_AUDIT.md).
- **Transactional Persistence & Rollback Safety:**
  - `models/app/crud/` enforces `try ... except Exception: db.rollback(); raise` across `create_vehicle`, `update_vehicle`, `delete_vehicle`, `create_user`, and `create_inspection` (atomically inserting inspection rows and updating parent `vehicles.health_score` & `latest_inspection_date`).

---

## 4. Database Security & Multi-Tenant Isolation

1. **Application-Layer Tenant Isolation (`user_id == current_user.id`):**
   - Customers can list, read, create, update, and delete **only** their own vehicles and inspections; probing unowned resources returns **HTTP 404** (anti-enumeration).
   - Admin accounts (`role == "admin"`) have fleet-wide visibility (including 5 legacy unassigned baseline vehicles).
   - Client role tampering is blocked via `extra="forbid"` Pydantic schemas and strict server-side `role="customer"` assignment on registration.
2. **PostgreSQL Least-Privilege Role (`autoinspect_app` via [`migrations/01_prepare_restricted_app_role.sql`](migrations/01_prepare_restricted_app_role.sql)):**
   - Flags: `LOGIN`, `NOINHERIT`, `NOBYPASSRLS`, `NOCREATEDB`, `NOCREATEROLE` (`rolsuper = false`, `rolreplication = false`).
   - Privileges: `USAGE` only on `public` (`CREATE` revoked from `PUBLIC` & `autoinspect_app`); `SELECT, INSERT` on `users`; `USAGE, SELECT` on `users_id_seq`; `SELECT, INSERT, UPDATE, DELETE` on `vehicles`; `SELECT, INSERT` on `inspections`; **zero grants** on the remaining 19 tables and **zero `EXECUTE`** for `PUBLIC` or `autoinspect_app` across all 4 `public` functions.
   - All 22 tables enable Row Level Security (`RLS`), with 8 policies scoped strictly `TO autoinspect_app` (`anon` and `PUBLIC` retain **0** table/sequence grants).
   - **Coordinated Production Cutover Status:** Verified end-to-end against `autoinspect_test`; production `.env` intentionally keeps `postgres` until operator-scheduled password rotation and cutover.

---

## 5. Verification & Testing Results (Executed on Isolated `autoinspect_test`)

All live mutation tests run exclusively against isolated `autoinspect_test` with safety gates verifying `current_database() == 'autoinspect_test'`. **Production database `postgres` remained untouched throughout all testing.**

| Verification Suite | Scope & Target | Result | Details |
| :--- | :--- | :---: | :--- |
| [`tests/test_restricted_role_live.py`](tests/test_restricted_role_live.py) | `autoinspect_app@autoinspect_test` E2E | **5 / 5 Phases PASS** | Session (`5432`), 8-thread concurrent Tx Pooler (`6543`), Direct IPv6 (`5432`), HTTP `TestClient` CRUD/RBAC/deep cascade, **17 negative privilege denials**, prod DB isolation |
| [`tests/test_database_persistence_isolation.py`](tests/test_database_persistence_isolation.py) | Persistence, JSONB & multi-tenant isolation | **13 / 13 PASS** | Customer A vs B 404 isolation, admin fleet visibility, JSONB fidelity, rollback & `ON DELETE CASCADE` |
| [`tests/test_crud_live.py`](tests/test_crud_live.py) | Live API CRUD lifecycle (`autoinspect_test`) | **8 / 8 PASS** | Create/Read/Update/Delete, 400/409/404 handling, baseline `5` vehicles & `57` inspections preserved |
| [`tests/test_backend.py`](tests/test_backend.py) | Backend + PostgreSQL regression suite | **10 / 10 PASS** | Seed idempotency, vehicle/inspection contracts, cascade delete, health check |
| [`tests/test_security_hardening.py`](tests/test_security_hardening.py) | FastAPI security controls (mocked DB) | **13 / 13 PASS** | TrustedHost, ASGI security headers, 15 MB limit, rate limiting, JWT & schema bounds (`0.191s`) |
| [`backup-recovery/run_complete_restore_test.py`](backup-recovery/run_complete_restore_test.py) | Complete `pg_catalog` logical SQL restore (`autoinspect_test`) | **10 / 10 PASS** | Restored 22 tables, 393 rows, 267 active cols, 7 seqs, 24 public constraints, 23 indexes, 4 funcs (`0` `PUBLIC` `EXECUTE`), `23` surfaced `auth` skips |
| PG 17.11 `pg_dump` / `pg_restore` | Offline binary custom archive (`136,881 B`) -> `autoinspect_test` | **PASS (`exit=0`)** | Filtered TOC `--use-list --single-transaction --exit-on-error` (`stderr=''`); 100% parity |

---

## 6. Backup & Recovery Architecture

1. **Native PostgreSQL 17.11 Custom Archive (Offline / Excluded from Public Repo):**
   - Generated read-only via `pg_dump --schema=public --format=custom --compress=9 --no-owner` (`136,881 bytes`, SHA-256: `B8938A9CDCC549F511ED8E7865588F3A3A6BFFB4BA3A007A75E8337C60281287`).
   - Validated via `pg_restore -l` (`206` TOC entries) and clean filtered restoration onto `autoinspect_test`.
2. **Python `pg_catalog` Logical SQL Exporter ([`backup-recovery/generate_complete_backup.py`](backup-recovery/generate_complete_backup.py)):**
   - Enables deterministic single-transaction (`BEGIN ... COMMIT`) logical exports and JSON manifests (`schema/complete_backup_manifest.json`) even on hosts without native `psql`/`pg_dump` binaries installed globally.
3. **Two-Phase Recovery Engine ([`backup-recovery/run_restore_test.py`](backup-recovery/run_restore_test.py) + [`schema/schema_ddl.sql`](schema/schema_ddl.sql)):**
   - Demonstrates why `NOT VALID` constraints (`inspections_vehicle_id_required`) and FKs must apply post-data when restoring legacy unlinked records.

---

## 7. Known Limitations & Pending Cutover Items

1. **Public Schema Scope Only:** Repository scripts target PostgreSQL's `public` schema; Supabase `auth`, `storage`, `realtime`, `vault` schemas and cluster roles are managed separately via Supabase PITR.
2. **Supabase `DEFAULT ACL` Auto-Grants (`pg_default_acl`):** Production `pg_catalog.pg_default_acl` in `public` auto-grants `ALL` on newly created tables/sequences/functions to `anon`, `authenticated`, and `service_role`. Future DDL migrations adding objects in `public` must explicitly run `REVOKE ALL ... FROM PUBLIC, anon` and enable RLS.
3. **Coordinated Production Role Cutover Pending:** Production `backend/.env` continues using `postgres` until operator-approved secret generation, migration execution on `postgres`, and `DATABASE_URL` cutover to `autoinspect_app`.
4. **Single-Role Application Pool:** Row-level ownership relies on audited FastAPI ORM scoping (`user_id == current_user.id`) unless transaction-local `SET LOCAL` session variables are layered in Phase 2.

---

## 8. Project Completion Status

- **Branch 1 Database Implementation, Hardening, Verification & Documentation:** **COMPLETE**
- **Test Execution Status:** **100% PASS** across all isolated database, restricted-role, restore-parity, CRUD, and security test suites (`0` failures, `0` skips).
- **Production Cutover Status:** **Prepared & Verified on `autoinspect_test`** — awaiting coordinated operator approval to apply on production.
