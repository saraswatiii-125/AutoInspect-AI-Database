# AutoInspect AI — Database Restore Verification Specification

**Branch:** Branch 1  
**Verification Target:** `autoinspect_test` (Isolated PostgreSQL Database)  
**Execution Timestamp:** November 8, 2026 (Live Verified)  
**Overall Status:** **PASS** (100% Success)

---

## 1. Scope & Verification Methodology

This document details the rigorous post-restoration verification executed against the restored test database `autoinspect_test`. Verification was performed using programmatic read-only inspection scripts and isolated transactional assertion tests.

---

## 2. Restored Database Object Inventory

### 2.1 Table Inventory & Physical Row Counts

| Schema | Table Name | Type | Primary Key | Foreign Key Dependencies | Restored Rows |
| :--- | :--- | :--- | :--- | :--- | :---: |
| `public` | `vehicles` | Base Table | `id` (TEXT) | `user_id -> users.id`, `owner_id -> profiles.id` | **5** |
| `public` | `inspections` | Base Table | `id` (TEXT) | `vehicle_id -> vehicles.id`, `user_id -> users.id` | **57** |
| `public` | `damage_detections` | Base Table | `id` (UUID) | `inspection_id -> inspections.inspection_id` | **69** |
| `public` | `detected_damages` | Base Table | `id` (INTEGER) | `inspection_id -> inspections.id` | **2** |
| `public` | `users` | Base Table | `id` (INTEGER) | None | **0** |
| `public` | `profiles` | Base Table | `id` (UUID) | None | **0** |
| `public` | `detections` | Base Table | `id` (INTEGER) | `inspection_id -> inspections.id` | **0** |
| `public` | `reports` | Base Table | `id` (INTEGER) | `inspection_id -> inspections.id` | **0** |
| `public` | `regions` | Base Table | `id` (JSONB) | None | **0** |

---

## 3. Constraint & Relationship Verification Results

### 3.1 Primary Key Enforcement (Negative Assertion)
- **Test:** Attempted to insert a duplicate vehicle record with `id = '1'`.
- **Query:** `INSERT INTO public.vehicles (id, make, model, year, registration, color, image) VALUES ('1', 'BMW', 'Duplicate', 2023, 'DIFF-REG', 'White', 'img');`
- **Result:** **REJECTED** with `psycopg.errors.UniqueViolation: duplicate key value violates unique constraint "vehicles_pkey"`.
- **Verdict:** **PASS**.

### 3.2 Unique Key Enforcement (Registration)
- **Test:** Attempted to insert a new vehicle with duplicate registration number `'MH-12-AB-2026'`.
- **Query:** `INSERT INTO public.vehicles (id, make, model, year, registration, color, image) VALUES ('new_v', 'BMW', 'UniqueTest', 2023, 'MH-12-AB-2026', 'White', 'img');`
- **Result:** **REJECTED** with `psycopg.errors.UniqueViolation: duplicate key value violates unique constraint "vehicles_registration_key"`.
- **Verdict:** **PASS**.

### 3.3 Foreign Key Integrity: `damage_detections` to `inspections.inspection_id`
- **Audit Query:**
  ```sql
  SELECT COUNT(*) FROM public.damage_detections dd
  WHERE NOT EXISTS (SELECT 1 FROM public.inspections i WHERE i.inspection_id = dd.inspection_id);
  ```
- **Result:** **0 orphan records.** All 69 damage detections resolve to valid UUID `inspections.inspection_id` parent rows.
- **Verdict:** **PASS**.

### 3.4 Foreign Key Integrity: `detected_damages` to `inspections.id`
- **Audit Query:**
  ```sql
  SELECT COUNT(*) FROM public.detected_damages dam
  WHERE NOT EXISTS (SELECT 1 FROM public.inspections i WHERE i.id = dam.inspection_id);
  ```
- **Result:** **0 orphan records.** Both records resolve to valid parent `inspections.id` rows.
- **Verdict:** **PASS**.

### 3.5 Foreign Key Integrity: `inspections` to `vehicles.id`
- **Audit Query:**
  ```sql
  SELECT COUNT(*) FROM public.inspections i
  WHERE i.vehicle_id IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM public.vehicles v WHERE v.id = i.vehicle_id);
  ```
- **Result:** **0 orphan records.** All 49 linked inspections resolve to valid baseline vehicles (`1` and `string`).
- **Verdict:** **PASS**.

### 3.6 Foreign Key Rejection (Negative Assertion)
- **Test:** Attempted to insert a child row into `damage_detections` with non-existent parent `inspection_id = 'non-existent-uuid'`.
- **Result:** **REJECTED** with `psycopg.errors.ForeignKeyViolation: insert or update on table "damage_detections" violates foreign key constraint "damage_detections_inspection_id_fkey"`.
- **Verdict:** **PASS**.

### 3.7 Check Constraint: Confidence Range
- **Test:** Attempted to insert a row into `damage_detections` with invalid `confidence = 1.8`.
- **Constraint:** `CHECK (confidence >= 0 AND confidence <= 1)`
- **Result:** **REJECTED** with `psycopg.errors.CheckViolation: new row violates check constraint "damage_detections_confidence_check"`.
- **Verdict:** **PASS**.

### 3.8 Check Constraint: `inspections_vehicle_id_required` (NOT VALID)
- **Test:** Attempted to insert a new inspection record with `vehicle_id = NULL`.
- **Constraint:** `CHECK (vehicle_id IS NOT NULL) NOT VALID`
- **Result:** **REJECTED** with `psycopg.errors.CheckViolation: new row violates check constraint "inspections_vehicle_id_required"`.
- **Verdict:** **PASS**. Historical unlinked rows (such as ID `30`) are preserved while new rows strictly require `vehicle_id`.

---

## 4. JSONB Column Contents & Structural Integrity

Sample queries executed against `inspections.damages`, `inspections.images`, and `inspections.ai_insights` verified that PostgreSQL JSONB fields decoded cleanly into native Python arrays and dictionaries:

| Inspection ID | `damages` Type | `images` Type | `ai_insights` Type | JSON Integrity Status |
| :--- | :--- | :--- | :--- | :--- |
| `string` | `list` (`[]`) | `list` (`[]`) | `list` (`[]`) | **VALID** |
| `4` | `list` (`[]`) | `list` (`[]`) | `list` (`[]`) | **VALID** |
| `30` | `list` (`[]`) | `list` (`[]`) | `list` (`[]`) | **VALID** |
| `31` | `list` (`[]`) | `list` (`[]`) | `list` (`[]`) | **VALID** |
| `32` | `list` (`[]`) | `list` (`[]`) | `list` (`[]`) | **VALID** |

---

## 5. Sample Read-Only Queries on Restored Data

### 5.1 Sample Vehicle Lookup
```sql
SELECT id, make, model, registration, color, health_score 
FROM public.vehicles WHERE id = '1';
```
**Returned Record:**
```json
{
  "id": "1",
  "make": "BMW",
  "model": "5 Series 530d",
  "registration": "MH-12-AB-2026",
  "color": "Alpine White",
  "health_score": 100
}
```
*Confirmed complete data accuracy.*

### 5.2 Sample Inspection Lookup
```sql
SELECT id, vehicle_id, overall_score, date, filename 
FROM public.inspections WHERE id = '4';
```
**Returned Record:**
```json
{
  "id": "4",
  "vehicle_id": "1",
  "overall_score": 85,
  "date": "2026-10-25",
  "filename": "test.jpg"
}
```
*Confirmed complete data accuracy.*

---

## 6. PostgreSQL Index Catalog Audit on Restored Database

13 indexes were verified in `pg_indexes` for core tables in `autoinspect_test`:

| Table Name | Index Name | Index Definition | Status |
| :--- | :--- | :--- | :--- |
| `damage_detections` | `damage_detections_pkey` | `UNIQUE (id)` | **ACTIVE** |
| `damage_detections` | `idx_damage_detections_inspection_id` | `btree (inspection_id)` | **ACTIVE** |
| `detected_damages` | `detected_damages_pkey` | `UNIQUE (id)` | **ACTIVE** |
| `detected_damages` | `idx_detected_damages_inspection_id` | `btree (inspection_id)` | **ACTIVE** |
| `inspections` | `inspections_pkey` | `UNIQUE (id)` | **ACTIVE** |
| `inspections` | `inspections_inspection_id_key` | `UNIQUE (inspection_id)` | **ACTIVE** |
| `inspections` | `idx_inspections_created_at` | `btree (created_at DESC)` | **ACTIVE** |
| `inspections` | `idx_inspections_user_id` | `btree (user_id)` | **ACTIVE** |
| `inspections` | `idx_inspections_vehicle_id` | `btree (vehicle_id)` | **ACTIVE** |
| `vehicles` | `vehicles_pkey` | `UNIQUE (id)` | **ACTIVE** |
| `vehicles` | `vehicles_registration_key` | `UNIQUE (registration)` | **ACTIVE** |
| `vehicles` | `idx_vehicles_owner_id` | `btree (owner_id)` | **ACTIVE** |
| `vehicles` | `idx_vehicles_user_id` | `btree (user_id)` | **ACTIVE** |

---

## 7. Final Verification Conclusion

| Verification Item | Requirement | Result |
| :--- | :--- | :---: |
| Expected Tables Restored | All 9 tables exist | **PASS** |
| Record Count Parity | Exactly 5 vehicles, 57 inspections, 69 damage detections, 2 detected damages | **PASS** |
| Primary Key Integrity | Rejects duplicate primary keys | **PASS** |
| Foreign Key Integrity | All foreign keys resolve cleanly with 0 orphans | **PASS** |
| Foreign Key Enforcement | Rejects orphan child insertions | **PASS** |
| Check Constraints | Enforces confidence range & rejects new NULL vehicle_id | **PASS** |
| JSONB Preservation | JSONB array/object data intact | **PASS** |
| Index Coverage | All 13 core indexes present and active | **PASS** |
| Production Isolation | Production database untouched | **PASS** |

**OVERALL VERIFICATION VERDICT (PHASE A):** **PASS**

---

## 8. Complete Single-Pass `pg_catalog` SQL & Native PG 17 `pg_restore` Parity Verification (November 12, 2026)

Following generation of both the native PostgreSQL 17.11 archive (``autoinspect_native_pg17.dump``, 136,881 bytes) and the self-contained `pg_catalog` logical SQL export (``autoinspect_complete_backup.sql``, 398,867 bytes), both artifacts were independently restored onto clean `autoinspect_test` and compared against live `postgres`:

| Catalog Dimension | Production (`postgres`) | Restored (`autoinspect_test`) | Status | Notes |
| :--- | :---: | :---: | :---: | :--- |
| Public Tables & Columns | 22 tables / 267 active cols | 22 tables / 267 active cols | **100% MATCH** | `ROW_NUMBER()` ignores dropped `vehicles` `attnum=6` tombstone |
| Total Data Rows | 393 | 393 | **100% MATCH** | `vehicles=5`, `inspections=57`, `damage_detections=69`, `detected_damages=2`, `inspections_migration_checkpoint_20261101=56`, other snapshots=204 |
| Sequence Cursor States | 7 | 7 | **100% MATCH** | Exact `last_value` & `is_called`; live `nextval('inspections_id_seq') == 57` verified |
| Public Constraints | 24 (+1 `auth.users` FK) | 24 | **100% MATCH** | `13` PK/UK + `3` CHECK + `8` public FK; `auth.users` FK safely skipped (`profiles_id_fkey`) |
| Public Indexes | 23 | 23 | **100% MATCH** | `13` constraint-backing + `10` standalone (incl. partial unique `idx_vehicles_code`) |
| Functions, ACLs & Triggers | 4 funcs (`0` PUBLIC `EXECUTE`), 1 `public` trigger (+2 `auth.users`) | 4 funcs (`0` PUBLIC `EXECUTE`), 1 `public` trigger | **100% MATCH** | Function `proacl` and `protect_profile_fields_trigger` matched; external `auth` triggers documented |
| RLS & Grants | 22 RLS enabled, 0 PUBLIC grants | 22 RLS enabled, 0 PUBLIC grants | **100% MATCH** | SQL logical restore emitted `23` expected skip notices (`26` total); filtered `pg_restore` exited `0` (`stderr=''`) |

**OVERALL VERIFICATION VERDICT (PHASE B SQL EXPORT + PHASE C PG 17 `pg_restore`):** **100% PASS**

