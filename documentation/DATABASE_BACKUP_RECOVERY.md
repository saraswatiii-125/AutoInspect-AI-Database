# AutoInspect AI — Database Backup & Disaster Recovery Runbook

**AutoInspect AI — Branch 1**  
**Document Date:** November 12, 2026 (Verified PG 17.11 Native `pg_dump`/`pg_restore` Archive & `pg_catalog` Logical Export)

---

> [!NOTE]
> **Public Repository Security Exclusion & Checksum Record:** Raw binary dumps (`autoinspect_native_pg17.dump`, SHA-256: `B8938A9CDCC549F511ED8E7865588F3A3A6BFFB4BA3A007A75E8337C60281287`) and data exports containing database rows or signed storage URLs (`autoinspect_complete_backup.sql`, `autoinspect_backup_verified.sql`, `autoinspect_backup_verified.json`) are stored offline and excluded from this public repository via `.gitignore`. All backups here strictly cover the **`public` schema only** and exclude Supabase-managed schemas (`auth`, `storage`, `realtime`, `supabase_functions`, `vault`) and cluster-wide roles.

## 1. Verified Backup Artifacts

Three backup artifacts exist in `code of UI/backend/`, each serving a clearly defined recovery scope:

### 1.1 Native PostgreSQL 17.11 Custom Archive (`pg_dump --format=custom`)
Generated read-only from live production `postgres` using PostgreSQL 17.11 `pg_dump` (`--schema=public --format=custom --compress=9 --no-owner`):

| Artifact | File Path | Size | Restoration Mode |
| :--- | :--- | :--- | :--- |
| **Native PG 17 Custom Dump** | ``code of UI/backend/autoinspect_native_pg17.dump`` | **136,881 bytes** | `pg_restore --no-owner --single-transaction --exit-on-error` (with TOC `--use-list` filtering Supabase `DEFAULT ACL` & `extensions` schema items when restoring as non-superuser `postgres`) |

### 1.2 Complete Single-File `pg_catalog` Logical SQL Export (Zero-Binary Portability)
Generated read-only from live `pg_catalog` introspection by [`generate_complete_backup.py`](../backup-recovery/generate_complete_backup.py):

| Artifact | File Path | Coverage | Restoration Mode |
| :--- | :--- | :--- | :--- |
| **Complete Logical SQL Export** | ``code of UI/backend/autoinspect_complete_backup.sql`` | **398,867 bytes** — `pg_catalog`-generated logical SQL export (not raw `pg_dump`): `SET search_path = public, extensions;`, extensions, 7 sequences, 22 tables, 393 rows (`INSERT` ordered deterministically by PK/`ctid`), 25 constraints (`NOT VALID` & `auth.users` FK guarded), 23 indexes, 4 functions + `proacl` (0 `PUBLIC` `EXECUTE`), `protect_profile_fields_trigger`, RLS & `aclexplode` grants (incl. `MAINTAIN`) | Single atomic transaction (`BEGIN; ... COMMIT;`) via `psql` or [`run_complete_restore_test.py`](../backup-recovery/run_complete_restore_test.py) |
| **Backup Manifest JSON** | [`code of UI/backend/autoinspect_complete_backup_manifest.json`](../schema/complete_backup_manifest.json) | Machine-readable inventory of all 22 table row counts, 7 sequence cursors, constraints, indexes, functions, and external `auth.users` trigger dependencies | Parity assertion reference |

### 1.3 Earlier Verified Snapshot Artifacts (Data Export Only)
> [!NOTE]
> Earlier documentation described `autoinspect_backup_verified.sql` as containing full DDL. Direct file audit (Nov 8, 2026) confirmed `autoinspect_backup_verified.sql` is a **data-only** (`INSERT`) export (116,670 bytes, 133 baseline rows across 9 core tables) that requires pre-data schema DDL (`schema_ddl.sql`) before loading. Use `autoinspect_native_pg17.dump` or `autoinspect_complete_backup.sql` for full disaster recovery.

| Artifact | File Path | Size | Description |
| :--- | :--- | :--- | :--- |
| **Data-Only SQL Export** | `code of UI/backend/autoinspect_backup_verified.sql` | 116,670 bytes | `BEGIN ... INSERT ... COMMIT` data-only export (133 core rows; requires `schema_ddl.sql`) |
| **JSON Snapshot Export** | `code of UI/backend/autoinspect_backup_verified.json` | 137,879 bytes | Structured JSON dump of tables, columns metadata, and core records |

### Verified Production Database Record Counts (All 22 Public Tables = 393 Rows)

- **Core Tables (10):** `vehicles` (5), `inspections` (57), `damage_detections` (69), `detected_damages` (2), `users` (0), `profiles` (0), `detections` (0), `reports` (0), `regions` (0), `id` (0).
- **Historical 2026-11-01 Snapshot Tables (12):** `damage_detections_backup_20261101` (69), `damage_detections_migration_checkpoint_20261101` (69), `detected_damages_backup_20261101` (2), `detected_damages_migration_checkpoint_20261101` (2), `detections_backup_20261101` (0), `detections_migration_checkpoint_20261101` (0), `inspections_backup_20261101` (56), `inspections_migration_checkpoint_20261101` (56), `reports_backup_20261101` (0), `reports_migration_checkpoint_20261101` (0), `vehicles_backup_20261101` (3), `vehicles_migration_checkpoint_20261101` (3).

---

## 2. Standard CLI Backup Procedure (`pg_dump`)

For automated cron jobs, CI/CD pipelines, or DBA workstations with PostgreSQL client tools installed:

### 2.1 Complete Schema and Data Backup
```bash
# Export full public schema with data, constraints, and indexes
pg_dump "postgresql://postgres.<project_ref>:[DB_PASSWORD]@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres?sslmode=require" \
  --schema=public \
  --format=plain \
  --no-owner \
  --no-acl \
  --file="backup_autoinspect_$(date +%Y%m%d_%H%M%S).sql"
```

### 2.2 Compressed Custom Format Backup (Recommended for large datasets)
```bash
pg_dump "postgresql://postgres.<project_ref>:[DB_PASSWORD]@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres?sslmode=require" \
  --schema=public \
  --format=custom \
  --compress=9 \
  --no-owner \
  --file="backup_autoinspect_$(date +%Y%m%d_%H%M%S).dump"
```

### 2.3 Python `pg_catalog` Logical Backup & Parity Verification Scripts
Because client PostgreSQL binaries may not be installed globally on every developer Windows workstation (`psql`/`pg_dump` are not required by runtime `.venv`), [`generate_complete_backup.py`](../backup-recovery/generate_complete_backup.py) exports the complete logical SQL dump + manifest via `pg_catalog` introspection:
```bash
cd "code of UI/backend"
.\.venv\Scripts\python.exe generate_complete_backup.py
```
To test single-pass atomic restoration into the isolated test database (`autoinspect_test`, **never `postgres`**):
```bash
cd "code of UI/backend"
.\.venv\Scripts\python.exe run_complete_restore_test.py
```

*(Legacy data-only script [`generate_backup.py`](../backup-recovery/generate_backup.py) + [`run_restore_test.py`](../backup-recovery/run_restore_test.py) remain available for 9-table JSON/data-only snapshots.)*

---

## 3. Disaster Recovery & Restoration Procedures

> [!CAUTION]
> **CRITICAL PRODUCTION SAFETY RULE:**
> NEVER restore a backup directly over the active production database! Always restore into an isolated staging or test database first, verify row counts and constraints, and execute an explicit rollback snapshot before touching production data.

### 3.1 Restoring into an Isolated Test/Staging Database
With PostgreSQL 17 CLI (`pg_restore` / `psql`), or programmatically via [`run_complete_restore_test.py`](../backup-recovery/run_complete_restore_test.py):

```bash
# Option A: Restore native PG 17 custom archive (filter Supabase DEFAULT ACL & extension schema items when target lacks superuser/supabase_admin)
pg_restore --list "code of UI/backend/autoinspect_native_pg17.dump" > full.toc
grep -v -E "SCHEMA - (extensions|public)|EXTENSION - |COMMENT - EXTENSION|DEFAULT ACL public|profiles_id_fkey|POLICY public" full.toc > filtered.toc
pg_restore -h <host> -p 5432 -U "postgres.<project_ref>" -d autoinspect_recovery_test \
  --no-owner --single-transaction --exit-on-error --use-list=filtered.toc \
  "code of UI/backend/autoinspect_native_pg17.dump"

# Option B: Restore self-contained pg_catalog logical SQL export in ONE pass
psql -h <host> -p 5432 -U "postgres.<project_ref>" -d autoinspect_recovery_test -v ON_ERROR_STOP=1 -f "code of UI/backend/autoinspect_complete_backup.sql"
```

Expected verification counts:
```
 vehicles_count | inspections_count | damage_detections_count | detected_damages_count 
----------------+-------------------+-------------------------+------------------------
              5 |                57 |                      69 |                      2
```

### 3.2 Production Point-in-Time Recovery (PITR) via Supabase
Because the production database is hosted on Supabase (PostgreSQL 17 on AWS), point-in-time recovery and automated daily WAL archiving are enabled at the platform tier:
1. Log in to the Supabase Management Console (`https://supabase.com/dashboard/project/<project_ref>`).
2. Navigate to **Database** -> **Backups**.
3. Select the desired Point-in-Time snapshot or scheduled daily backup.
4. Click **Restore to New Project** to inspect and validate without risking active production traffic.
5. Once verified, repoint `DATABASE_URL` in the production environment variables to the restored instance.

---

## 4. Verification Checklist & Known Portability Limitations

Before routing application traffic to a restored database, verify:
- [x] All **22 `public` tables** and **393 rows** match `autoinspect_complete_backup_manifest.json` (`vehicles=5`, `inspections=57`, `damage_detections=69`, `detected_damages=2`, `users=0`, `inspections_migration_checkpoint_20261101=56`, plus 11 other `*_20261101` snapshot tables).
- [x] All **7 sequences** match exact cursor states (`detected_damages_id_seq=(2, true)`, `inspections_id_seq=(56, true)`, `vehicles_id_seq=(3, true)`, etc.).
- [x] Zero orphan records exist in `inspections`, `damage_detections`, and `detected_damages`.
- [x] All **23 public indexes** (`13` PK/UK constraint-backing + `10` standalone, including partial unique `idx_vehicles_code` and FK indexes) are active.
- [x] All **4 public functions** preserve revoked `PUBLIC` `EXECUTE` ACLs (`0` `PUBLIC` `EXECUTE`).
- [x] Both `run_complete_restore_test.py` and PG 17.11 `pg_restore` verification pass against `autoinspect_test` with zero data loss.

### Known Backup / Restore Limitations
1. **Local Windows Binary Availability (`pg_dump` / `pg_restore`):** Native PostgreSQL client tools are not installed system-wide in the OS `PATH`. The PG 17.11 custom dump (``autoinspect_native_pg17.dump``) was created and tested using portable PG 17.11 binaries, while [`generate_complete_backup.py`](../backup-recovery/generate_complete_backup.py) provides an automated Python-native `pg_catalog` logical SQL export (`autoinspect_complete_backup.sql`) without external binary dependencies.
2. **Supabase `DEFAULT ACL` & Extension Permissions During `pg_restore`:** Running raw unfiltered `pg_restore` as Supabase non-superuser `postgres` onto a fresh DB emits non-fatal errors on `ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin` and `CREATE EXTENSION` / `COMMENT ON EXTENSION`. Using `--use-list` filtering (verified `exit=0, stderr=''` onto `autoinspect_test`) or Supabase full project PITR avoids these errors cleanly.
3. **Cross-Schema Supabase Auth Portability (`auth.users` / `auth.uid()` & External Triggers):** Non-Supabase vanilla targets (like `autoinspect_test`) lack Supabase's internal `auth` schema, `authenticated` / `service_role` roles, and `auth.users` triggers (`on_auth_user_created->handle_new_user()`, `on_auth_user_email_changed->handle_user_email_change()`). `autoinspect_complete_backup.sql` wraps `profiles_id_fkey` and 22 `auth.uid()` RLS policies in conditional `DO` blocks emitting explicit notices (`23` surfaced skips when restored on `autoinspect_test`), while full `auth`-schema restoration requires Supabase PITR/project backups.
