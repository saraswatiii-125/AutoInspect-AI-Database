# AutoInspect AI — Database Index Audit & Optimization Report

This document reports on the comprehensive index audit, missing foreign key index resolution, and query performance optimizations performed on the AutoInspect AI PostgreSQL database.

---

## 1. Complete Index Inventory (Live PostgreSQL 17.11)

Following the index optimization migrations, every table and foreign key in the `public` schema is indexed (**23 total `pg_indexes` entries** = **13 constraint-backing unique PK/UK indexes** + **10 standalone indexes**, including partial unique `idx_vehicles_code` and all FK indexes).

| Table Name | Index Name | Indexed Column | Uniqueness | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `damage_detections` | `damage_detections_pkey` | `id` | **UNIQUE** (PK) | Primary Key lookups |
| `damage_detections` | `idx_damage_detections_inspection_id` | `inspection_id` | NON-UNIQUE | FK lookup to `inspections.inspection_id` |
| `detected_damages` | `detected_damages_pkey` | `id` | **UNIQUE** (PK) | Primary Key lookups |
| `detected_damages` | `idx_detected_damages_inspection_id` | `inspection_id` | NON-UNIQUE | **[NEW]** FK lookup to `inspections.id` |
| `detections` | `detections_pkey` | `id` | **UNIQUE** (PK) | Primary Key lookups |
| `detections` | `idx_detections_inspection_id` | `inspection_id` | NON-UNIQUE | **[NEW]** FK lookup to `inspections.id` |
| `id` | `id_pkey` | `id` | **UNIQUE** (PK) | System identifier |
| `inspections` | `inspections_pkey` | `id` | **UNIQUE** (PK) | Primary Key lookups |
| `inspections` | `inspections_inspection_id_key` | `inspection_id` | **UNIQUE** | Target for `damage_detections_inspection_id_fkey` |
| `inspections` | `idx_inspections_vehicle_id` | `vehicle_id` | NON-UNIQUE | Filter by vehicle (`/api/inspections?vehicleId=...`) |
| `inspections` | `idx_inspections_user_id` | `user_id` | NON-UNIQUE | **[NEW]** Customer isolation filter (`user_id = :current_user`) |
| `inspections` | `idx_inspections_created_at` | `created_at` | NON-UNIQUE | Timestamp sorting (`ORDER BY created_at DESC`) |
| `profiles` | `profiles_pkey` | `id` | **UNIQUE** (PK) | Primary Key lookups |
| `regions` | `regions_pkey` | `id` | **UNIQUE** (PK) | Primary Key lookups |
| `reports` | `reports_pkey` | `id` | **UNIQUE** (PK) | Primary Key lookups |
| `reports` | `idx_reports_inspection_id` | `inspection_id` | NON-UNIQUE | **[NEW]** FK lookup to `inspections.id` |
| `users` | `users_pkey` | `id` | **UNIQUE** (PK) | Primary Key lookups |
| `users` | `users_email_key` | `email` | **UNIQUE** | Fast login / lookup by email (`/api/auth/login`) |
| `vehicles` | `vehicles_pkey` | `id` | **UNIQUE** (PK) | Primary Key lookups |
| `vehicles` | `vehicles_registration_key` | `registration` | **UNIQUE** | Unique license plate enforcement & collision checks |
| `vehicles` | `idx_vehicles_code` | `code` | **PARTIAL UNIQUE** (`WHERE code IS NOT NULL`) | Legacy vehicle identifier lookups (allows multiple NULLs) |
| `vehicles` | `idx_vehicles_user_id` | `user_id` | NON-UNIQUE | **[NEW]** Customer vehicle ownership filtering |
| `vehicles` | `idx_vehicles_owner_id` | `owner_id` | NON-UNIQUE | **[NEW]** Legacy profile lookup |

---

## 2. Foreign Key Index Audit & Optimizations

### 2.1 Missing Indexes Identified
Prior to optimization, PostgreSQL system catalogs were queried to detect all foreign key constraints lacking an index on the referencing columns:

```sql
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name,
    tc.constraint_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
  AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
  ON ccu.constraint_name = tc.constraint_name
  AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'public'
  AND NOT EXISTS (
      SELECT 1
      FROM pg_index ix
      JOIN pg_class t ON t.oid = ix.indrelid
      JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
      JOIN pg_namespace n ON n.oid = t.relnamespace
      WHERE n.nspname = 'public'
        AND t.relname = tc.table_name
        AND a.attname = kcu.column_name
  );
```

**Audit Result:** Six foreign keys were completely unindexed:
1. `vehicles.user_id -> users.id`
2. `inspections.user_id -> users.id`
3. `detected_damages.inspection_id -> inspections.id`
4. `detections.inspection_id -> inspections.id`
5. `reports.inspection_id -> inspections.id`
6. `vehicles.owner_id -> profiles.id`

### 2.2 Performance Impact of Missing FK Indexes
- **Customer Scoped Queries:** In the AutoInspect AI security model, every customer query executes:
  - `SELECT * FROM vehicles WHERE user_id = :current_user_id`
  - `SELECT * FROM inspections WHERE user_id = :current_user_id`
  Without indexes on `user_id`, PostgreSQL was forced to perform sequential scans (`Seq Scan`) across the entire table for every customer request.
- **Cascade Deletions:** When a user or inspection was deleted, PostgreSQL performed sequential scans on `detected_damages`, `reports`, and `detections` to verify or trigger foreign key cascade constraints.

### 2.3 Applied Optimizations
The following DDL statements were executed against live PostgreSQL:

```sql
CREATE INDEX IF NOT EXISTS idx_vehicles_user_id ON public.vehicles (user_id);
CREATE INDEX IF NOT EXISTS idx_inspections_user_id ON public.inspections (user_id);
CREATE INDEX IF NOT EXISTS idx_detected_damages_inspection_id ON public.detected_damages (inspection_id);
CREATE INDEX IF NOT EXISTS idx_detections_inspection_id ON public.detections (inspection_id);
CREATE INDEX IF NOT EXISTS idx_reports_inspection_id ON public.reports (inspection_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_owner_id ON public.vehicles (owner_id);
```

### 2.4 Verification
After applying the FK index migration DDL on November 8, 2026 (and re-verified via [`run_complete_restore_test.py`](../backup-recovery/run_complete_restore_test.py) and PG 17.11 `pg_restore` across all 23 `public` indexes on November 12, 2026), the audit query confirmed:
```
=== FOREIGN KEYS WITHOUT INDEXES ===
All foreign keys have indexes!
```
**Zero unindexed foreign keys remain.**

---

## 3. Query Performance Mapping to FastAPI Endpoints

| FastAPI Endpoint | HTTP Method | SQL Access Pattern | Utilizing Index | Performance Class |
| :--- | :--- | :--- | :--- | :--- |
| `/api/auth/login` | POST | `SELECT * FROM users WHERE email = :email` | `users_email_key` | **O(1)** Index Scan |
| `/api/vehicles` (Customer) | GET | `SELECT * FROM vehicles WHERE user_id = :uid` | `idx_vehicles_user_id` | **O(log N)** Bitmap Index Scan |
| `/api/vehicles/{id}` | GET | `SELECT * FROM vehicles WHERE id = :id` | `vehicles_pkey` | **O(1)** Index Scan |
| `/api/vehicles` (Admin) | GET | `SELECT * FROM vehicles ORDER BY id` | `vehicles_pkey` | **O(N)** Scan |
| `/api/inspections` (Customer) | GET | `SELECT * FROM inspections WHERE user_id = :uid` | `idx_inspections_user_id` | **O(log N)** Bitmap Index Scan |
| `/api/inspections?vehicleId=...` | GET | `SELECT * FROM inspections WHERE vehicle_id = :vid` | `idx_inspections_vehicle_id` | **O(log N)** Index Scan |
| `/api/inspections/{id}` | GET | `SELECT * FROM inspections WHERE id = :id` | `inspections_pkey` | **O(1)** Index Scan |
| Cascade Deletes | DELETE | `DELETE FROM child WHERE inspection_id = :id` | `idx_*_inspection_id` | **O(log N)** Index Scan (prevents table lock) |

