# AutoInspect AI — Database Entity Relationships & Foreign Key Architecture

This document provides a comprehensive technical audit and architectural specification of all foreign key relationships, data type mappings, and cascade behaviors in the AutoInspect AI PostgreSQL database.

---

## 1. Foreign Key Relationship Matrix

| Constraint Name | Source Table | Source Column | Target Table | Target Column | On Delete | On Update | Active Rows | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `vehicles_user_id_fkey` | `vehicles` | `user_id` (INTEGER) | `users` | `id` (INTEGER) | **CASCADE** | NO ACTION | Dynamic | VERIFIED (0 orphans) |
| `vehicles_owner_id_fkey` | `vehicles` | `owner_id` (UUID) | `profiles` | `id` (UUID) | **SET NULL** | NO ACTION | 0 / 5 | VERIFIED (Legacy) |
| `inspections_user_id_fkey` | `inspections` | `user_id` (INTEGER) | `users` | `id` (INTEGER) | **CASCADE** | NO ACTION | Dynamic | VERIFIED (0 orphans) |
| `inspections_vehicle_id_fkey`| `inspections`| `vehicle_id` (VARCHAR)| `vehicles` | `id` (VARCHAR) | **CASCADE** | NO ACTION | 49 / 57 | VERIFIED (0 orphans) |
| `damage_detections_inspection_id_fkey` | `damage_detections` | `inspection_id` (TEXT) | `inspections` | `inspection_id` (TEXT) | **CASCADE** | NO ACTION | 69 | VERIFIED (0 orphans) |
| `detected_damages_inspection_id_fkey` | `detected_damages` | `inspection_id` (VARCHAR) | `inspections` | `id` (VARCHAR) | **CASCADE** | NO ACTION | 2 | VERIFIED (0 orphans) |
| `detections_inspection_id_fkey` | `detections` | `inspection_id` (VARCHAR) | `inspections` | `id` (VARCHAR) | **CASCADE** | NO ACTION | 0 | VERIFIED (0 orphans) |
| `reports_inspection_id_fkey` | `reports` | `inspection_id` (VARCHAR) | `inspections` | `id` (VARCHAR) | **CASCADE** | NO ACTION | 0 | VERIFIED (0 orphans) |

---

## 2. In-Depth Resolution: `damage_detections` vs `inspections.inspection_id` vs `inspections.id`

### 2.1 The Architectural Discrepancy
Earlier system documentation noted ambiguity regarding whether child damage tables referenced `inspections.id` (numeric string, e.g. `'4'`, `'30'`) or a UUID identifier.

A rigorous database audit was executed to query `information_schema.table_constraints` and `pg_constraint` on PostgreSQL 17.11:

```sql
SELECT
    tc.constraint_name,
    kcu.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table,
    ccu.column_name AS foreign_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu
  ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND (kcu.table_name LIKE '%damage%' OR kcu.table_name = 'inspections');
```

### 2.2 Live Database Findings
1. **`inspections` has TWO identification columns:**
   - `inspections.id` (`VARCHAR`): Primary key. Contains values such as `'4'`, `'30'`, `'string'`, `'test_i_1'`.
   - `inspections.inspection_id` (`TEXT`): Has a unique constraint (`inspections_inspection_id_key`). Contains UUID values such as `'e5dbf53f-1367-4719-8250-8afaa40bb4a3'`.

2. **`damage_detections` (69 rows):**
   - References `inspections.inspection_id` (the UUID string column).
   - Foreign key constraint: `damage_detections_inspection_id_fkey`.
   - Action: `ON DELETE CASCADE`.
   - **Orphan Audit:** An SQL verification was executed:
     ```sql
     SELECT COUNT(*) FROM damage_detections d
     WHERE NOT EXISTS (SELECT 1 FROM inspections i WHERE i.inspection_id = d.inspection_id);
     ```
     **Result: Exactly 0 orphan records.** All 69 records match existing `inspections.inspection_id` rows.

3. **`detected_damages` (2 rows):**
   - References `inspections.id` (the numeric string primary key column).
   - Foreign key constraint: `detected_damages_inspection_id_fkey`.
   - Action: `ON DELETE CASCADE`.
   - **Orphan Audit:** Exactly 0 orphan records.

4. **Modern Application Architecture (JSONB Model):**
   - In the modern FastAPI application, damage detections are embedded directly in the `inspections.damages` `JSONB` column, while images and bounding boxes are embedded in `inspections.images` `JSONB`.
   - This eliminates complex multi-table joins during real-time inspection visualization, while the normalized tables (`damage_detections`, `detected_damages`) remain fully consistent and intact for historical analytics.

---

## 3. Vehicle-to-Inspection Relationship

- **Parent:** `vehicles.id` (`VARCHAR`, PK)
- **Child:** `inspections.vehicle_id` (`VARCHAR`, FK)
- **Constraint:** `inspections_vehicle_id_fkey`
- **Deletion Rule:** `ON DELETE CASCADE`
  - Deleting a vehicle automatically removes all associated inspection records.
  - Verified live in both `test_crud_live.py` (Case 8) and `test_database_persistence_isolation.py` (Case 6.3).

### Unassigned Inspections Note
- Out of 57 baseline inspections, 49 are linked to baseline vehicles (48 for Vehicle 1, 1 for Vehicle `string`).
- 8 historical inspections have `vehicle_id = NULL`.
- The `inspections_vehicle_id_required` CHECK constraint was created with `NOT VALID`, which enforces `vehicle_id IS NOT NULL` on newly created records while preserving the legacy records without data loss.

---

## 4. Multi-Tenant User Ownership Relationships

- **Users to Vehicles:**
  - Foreign key: `vehicles_user_id_fkey` (`vehicles.user_id -> users.id`)
  - Type: `INTEGER` -> `INTEGER`
  - Rule: `ON DELETE CASCADE`
  - Multi-tenant boundary: Customer users can only read, update, or delete vehicles where `vehicles.user_id == current_user.id`.

- **Users to Inspections:**
  - Foreign key: `inspections_user_id_fkey` (`inspections.user_id -> users.id`)
  - Type: `INTEGER` -> `INTEGER`
  - Rule: `ON DELETE CASCADE`
  - Multi-tenant boundary: Customer users can only access inspections where `inspections.user_id == current_user.id`.

---

## 5. Deletion Cascades & Transaction Integrity Summary

```
users (PK: id)
  ├── ON DELETE CASCADE ──> vehicles (FK: user_id)
  │                            └── ON DELETE CASCADE ──> inspections (FK: vehicle_id)
  │                                                         ├── ON DELETE CASCADE ──> damage_detections (FK: inspection_id)
  │                                                         ├── ON DELETE CASCADE ──> detected_damages (FK: inspection_id)
  │                                                         ├── ON DELETE CASCADE ──> detections (FK: inspection_id)
  │                                                         └── ON DELETE CASCADE ──> reports (FK: inspection_id)
  └── ON DELETE CASCADE ──> inspections (FK: user_id)
```

1. Deleting a `users` row removes all vehicles and inspections owned by that user.
2. Deleting a `vehicles` row cascades to delete all linked `inspections`.
3. Deleting an `inspections` row cascades to delete all linked child records in `damage_detections`, `detected_damages`, `detections`, and `reports`.
4. Deleting a legacy `profiles` row sets `vehicles.owner_id` to `NULL` (`ON DELETE SET NULL`), preserving the vehicle data.

