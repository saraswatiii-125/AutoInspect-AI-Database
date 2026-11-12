# AutoInspect AI — Database Schema Specification

This document provides the definitive, live-verified PostgreSQL schema specification for the AutoInspect AI application (Supabase PostgreSQL 17.11, verified against `pg_catalog` on November 12, 2026).

---

## 1. Physical Schema Overview

The PostgreSQL `public` schema contains **22 tables** totaling **393 baseline rows**:
- **10 Core / Schema Tables** (`users`, `profiles`, `vehicles`, `inspections`, `damage_detections`, `detected_damages`, `detections`, `reports`, `regions`, `id`).
- **12 Historical 2026-11-01 Snapshot & Checkpoint Tables** (`*_backup_20261101` and `*_migration_checkpoint_20261101` for `damage_detections`, `detected_damages`, `detections`, `inspections`, `reports`, `vehicles`).

### Active / Schema Table Summary

| Table | Primary Key | Description | Live Row Count |
| :--- | :--- | :--- | :--- |
| `users` | `id` (`integer`, `users_id_seq`) | Authentication credentials, Argon2id hashes, roles | 0 baseline (dynamic) |
| `profiles` | `id` (`uuid`, FK -> `auth.users.id`) | Legacy Supabase Auth profile records | 0 |
| `vehicles` | `id` (`text`) | Fleet vehicles, make, model, year, registration | 5 baseline |
| `inspections` | `id` (`text`) | AI inspections, scores, costs, damages/images JSONB | 57 baseline |
| `damage_detections` | `id` (`uuid`) | YOLO bounding-box detections (FK -> `inspections.inspection_id`) | 69 baseline |
| `detected_damages` | `id` (`integer`, `detected_damages_id_seq`) | Secondary damage detections (FK -> `inspections.id`) | 2 baseline |
| `detections` | `id` (`integer`, `detections_id_seq`) | Vision detection bounding boxes (FK -> `inspections.id`) | 0 |
| `reports` | `id` (`integer`, `reports_id_seq`) | Formal inspection report PDF paths (FK -> `inspections.id`) | 0 |
| `regions` | `id` (`jsonb`) | Legacy geographic region payload table | 0 |
| `id` | `id` (`bigint`, IDENTITY `id_id_seq`) | Standalone system timestamp / sequence table | 0 |

---

## 2. Table-by-Table Column Specifications

### 2.1 Table: `users`
Primary authentication table supporting custom FastAPI JWT authentication and Argon2id hashing.

| Column | Type | Nullable | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `integer` | NO | `nextval('users_id_seq'::regclass)` | PK (`users_pkey`) | Unique integer identifier |
| `email` | `varchar(255)` | NO | None | UNIQUE (`users_email_key`) | Normalized lowercase email address |
| `hashed_password`| `varchar(255)` | NO | None | None | Argon2id password hash |
| `role` | `varchar(50)` | NO | `'customer'::varchar` | Enforced in FastAPI (`'customer'` / `'admin'`) | Application RBAC role |
| `created_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` | None | Account creation timestamp (UTC) |

### 2.2 Table: `vehicles`
Represents registered customer and fleet vehicles *(15 active columns across 16 `pg_attribute` slots due to an inherited dropped column tombstone `attisdropped = true` at `attnum=6`; schema parity across all 22 tables totals 267 active columns)*.

| Column | Type | Nullable | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `text` | NO | None | PK (`vehicles_pkey`) | Alphanumeric or UUID-based vehicle ID |
| `user_id` | `integer` | YES | `NULL` | FK -> `users.id` ON DELETE CASCADE | Owner user ID (multi-tenant boundary) |
| `owner_id` | `uuid` | YES | `NULL` | FK -> `profiles.id` ON DELETE SET NULL | Legacy Supabase profile link |
| `make` | `varchar(100)` | NO | None | None | Vehicle manufacturer (e.g. BMW) |
| `model` | `varchar(100)` | NO | None | None | Model name (e.g. 5 Series 530d) |
| `year` | `integer` | NO | None | None | Manufacture year (legacy baseline >= 0; API create >= 1900) |
| `registration` | `text` | NO | None | UNIQUE (`vehicles_registration_key`) | Unique license/registration plate |
| `color` | `text` | NO | `'Alpine White'::text` | None | Vehicle exterior color |
| `image` | `text` | NO | None | None | Active image URL or data URI |
| `image_url` | `text` | YES | `NULL` | None | Historical Supabase image URL |
| `health_score` | `integer` | YES | `100` | None | Overall fleet health (0–100) |
| `latest_inspection_date`| `text` | YES | `NULL` | None | ISO date string of latest inspection |
| `code` | `text` | YES | `NULL` | Partial UNIQUE `idx_vehicles_code WHERE (code IS NOT NULL)` | Legacy vehicle reference code |
| `created_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` | None | Creation timestamp |
| `updated_at` | `timestamptz` | YES | `timezone('utc', now())` | None | Last modification timestamp (UTC) |

### 2.3 Table: `inspections`
Inspection runs containing AI assessment, damages, and images.

| Column | Type | Nullable | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `text` | NO | None | PK (`inspections_pkey`) | Alphanumeric/string inspection ID (e.g. `'4'`) |
| `inspection_id` | `text` | YES | `NULL` | UNIQUE (`inspections_inspection_id_key`) | UUID string referenced by `damage_detections` |
| `vehicle_id` | `text` | YES | `NULL` | FK -> `vehicles.id` ON DELETE CASCADE; CHECK (`NOT VALID`) | Parent vehicle ID (new rows require NOT NULL) |
| `user_id` | `integer` | YES | `NULL` | FK -> `users.id` ON DELETE CASCADE | Creator user ID |
| `date` | `text` | NO | None | None | Inspection date string (`YYYY-MM-DD`) |
| `status` | `text` | YES | `'completed'::text` | None | Status (`completed`, `pending`, `in_progress`) |
| `overall_score` | `integer` | YES | `80` | None | Health score calculated from AI assessment |
| `total_cost_min`| `integer` | YES | `0` | None | Minimum estimated repair cost |
| `total_cost_max`| `integer` | YES | `0` | None | Maximum estimated repair cost |
| `estimated_cost_min`| `double precision` | YES | `NULL` | None | Legacy cost float min |
| `estimated_cost_max`| `double precision` | YES | `NULL` | None | Legacy cost float max |
| `filename` / `image_name` / `image_path` | `text` | YES | `NULL` | None | Legacy YOLO image metadata |
| `annotated_image_url` / `original_image_url` | `text` | YES | `NULL` | None | Signed Supabase storage URLs |
| `detection_count` | `integer` | YES | `0` | None | Legacy YOLO box count |
| `note` | `text` | YES | `NULL` | None | AI summary/inspection note |
| `ai_insights` | `jsonb` | YES | `'[]'::jsonb` | None | List of AI insight strings |
| `damages` | `jsonb` | YES | `'[]'::jsonb` | None | Array of structured damage objects |
| `images` | `jsonb` | YES | `'[]'::jsonb` | None | Array of inspection image objects |
| `created_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` | None | Creation timestamp |
| `updated_at` | `timestamptz` | YES | `timezone('utc', now())` | None | Update timestamp |

### 2.4 Table: `damage_detections`
Normalized YOLO bounding-box detection records referencing `inspections.inspection_id` (69 rows).

| Column | Type | Nullable | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `uuid` | NO | `gen_random_uuid()` | PK (`damage_detections_pkey`) | UUID primary key |
| `inspection_id` | `text` | NO | None | FK -> `inspections.inspection_id` ON DELETE CASCADE | Parent inspection UUID string |
| `class_id` | `integer` | NO | None | None | YOLO dataset damage class ID |
| `class_name` | `text` | NO | None | None | Damage class label/ID string |
| `confidence` | `numeric(5,4)` | NO | None | CHECK (`confidence >= 0 AND confidence <= 1`) | Model confidence score |
| `box_x1`, `box_y1`, `box_x2`, `box_y2` | `numeric(8,2)` | NO | None | None | Pixel bounding-box coordinates |
| `created_at` | `timestamptz` | NO | `timezone('utc', now())` | None | Detection timestamp |

### 2.5 Table: `detected_damages` & `detections`
Legacy / secondary normalized damage tables referencing `inspections.id` (`detected_damages`: 2 rows; `detections`: 0 rows).

| Column Group | Type | Default / Constraint | Description |
| :--- | :--- | :--- | :--- |
| `id` | `integer` (NOT NULL) | `nextval('detected_damages_id_seq')` / `nextval('detections_id_seq')` (PK) | Integer sequence primary key |
| `inspection_id` | `text` (NULL) | FK -> `inspections.id` ON DELETE CASCADE | Parent inspection ID |
| `image_url`, `damage_type`, `severity`, `confidence_score`, `bbox_coordinates`, `repair_recommendation` | `varchar` / `double` / `text` | Nullable | Legacy textual detection attributes |
| `class_id`, `class_name`, `confidence`, `box_x1..y2`, `created_at` | `integer` / `text` / `numeric` / `timestamptz` | Nullable | Unified normalized detection attributes (`detected_damages` also adds nullable numeric `x_min`, `ymin`, `x_max`, `ymax`) |

### 2.6 Table: `reports`
Inspection PDF export metadata referencing `inspections.id` (0 rows).

| Column | Type | Nullable | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `integer` | NO | `nextval('reports_id_seq'::regclass)` | PK (`reports_pkey`) | Integer primary key |
| `inspection_id` | `text` | YES | `NULL` | FK -> `inspections.id` ON DELETE CASCADE | Referenced inspection |
| `pdf_report_path` | `varchar(255)` | NO | None | None | PDF output path |
| `generated_at` | `timestamp` | YES | `CURRENT_TIMESTAMP` | None | Generation timestamp |

### 2.7 Table: `profiles`, `regions`, & `id`
- **`profiles`** (`0 rows`): Supabase Auth profile mirror (`id uuid` PK + FK -> `auth.users(id) ON DELETE CASCADE`, `email text NOT NULL`, `full_name text`, `role text NOT NULL DEFAULT 'customer' CHECK ('customer','admin')`, `created_at timestamptz`, `updated_at timestamptz`; protected by `protect_profile_fields_trigger`).
- **`regions`** (`0 rows`): Legacy table (`id jsonb NOT NULL` PK, `created_at timestamptz NOT NULL DEFAULT now()`, `inspection_id bigint`).
- **`id`** (`0 rows`): Auxiliary identity table (`id bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL` PK, `created_at timestamptz NOT NULL DEFAULT now()`).

### 2.8 Historical 2026-11-01 Snapshot & Checkpoint Tables (12 Tables, 260 Rows)
Non-runtime historical snapshots retained verbatim in backups: `damage_detections_backup_20261101` (69), `damage_detections_migration_checkpoint_20261101` (69), `detected_damages_backup_20261101` (2), `detected_damages_migration_checkpoint_20261101` (2), `detections_backup_20261101` (0), `detections_migration_checkpoint_20261101` (0), `inspections_backup_20261101` (56), `inspections_migration_checkpoint_20261101` (56), `reports_backup_20261101` (0), `reports_migration_checkpoint_20261101` (0), `vehicles_backup_20261101` (3), `vehicles_migration_checkpoint_20261101` (3).

### 2.9 Extensions, Functions & Cross-Schema Triggers
- **Extensions:** `pgcrypto` and `uuid-ossp` reside in the `extensions` schema; `damage_detections.id` default `gen_random_uuid()` resolves to built-in `pg_catalog.gen_random_uuid()` (verified with `SET search_path = public, extensions;`).
- **Functions & Triggers:** 4 user-defined functions live in `public` (`handle_new_user()`, `handle_user_email_change()`, `is_admin()`, `protect_profile_fields()`), all with `PUBLIC` `EXECUTE` revoked. 1 trigger resides inside `public` (`protect_profile_fields_trigger` on `public.profiles`), while 2 triggers live in Supabase's `auth` schema (`auth.users`: `on_auth_user_created -> handle_new_user()`, `on_auth_user_email_changed -> handle_user_email_change()`).

---

## 3. Schema vs Application Model Synchronization

| Entity | DB Table | SQLAlchemy Model | Pydantic Schema | Aliases / Serialization |
| :--- | :--- | :--- | :--- | :--- |
| User | `users` | `UserModel` | `UserResponse`, `UserLoginRequest` | `createdAt`, `id`, `email`, `role` |
| Vehicle | `vehicles` | `VehicleModel` | `VehicleCreate`, `VehicleUpdate`, `VehicleResponse` | `healthScore`, `latestInspectionDate`, `inspections` |
| Inspection | `inspections` | `InspectionModel` | `CreateInspectionRequestSchema`, `InspectionResponse` | `vehicleId`, `overallScore`, `totalCostMin`, `totalCostMax`, `aiInsights`, `damages`, `images` |
| Damage | `inspections.damages` (JSONB) | Embedded in `InspectionModel.damages` | `DamageSchema` | `costMin`, `costMax`, `imageIndex`, `bbox` (`x`, `y`, `w`, `h`) |

---

## 4. Legacy Data and Integrity Rules

1. **Unassigned Legacy Vehicles (5 records):**
   - The 5 baseline vehicles (`1`, `2`, `3`, `v_1793622734600`, `string`) have `user_id = NULL`.
   - Admin users have full access to view, inspect, and manage these records.
   - Customer accounts cannot access or claim unassigned vehicles unless explicitly assigned by an administrator.

2. **Unassigned Legacy Inspections (8 records):**
   - 8 historical inspection records have `vehicle_id = NULL`.
   - The database constraint `inspections_vehicle_id_required` was added with `NOT VALID`, which guarantees that all future inspections require a valid `vehicle_id`, while strictly preserving the integrity of historical rows.

