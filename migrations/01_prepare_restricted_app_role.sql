-- =============================================================================
-- AutoInspect AI - Dedicated Restricted Application Database Role Migration
-- Target: Supabase PostgreSQL 17.11
--
-- SAFETY NOTICE:
--   1. Apply Parts B & C to `autoinspect_test` FIRST and validate all tests.
--   2. Coordinate cutover before applying Parts B & C to production (`postgres`)
--      and before changing `DATABASE_URL` in `backend/.env`.
--   3. Replace `<REPLACE_WITH_STRONG_256BIT_PASSWORD>` securely in memory/vault;
--      NEVER commit real passwords to version control.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- PART A: CLUSTER-WIDE RESTRICTED ROLE DEFINITION
-- Note: Managed PostgreSQL `postgres` on Supabase has `rolsuper = false` and
-- PG 17 rejects `ALTER ROLE ... NOSUPERUSER` / `NOREPLICATION` without
-- superuser. Omitting them creates a non-superuser, non-replication role by
-- default; the explicit verification query below asserts all boolean flags.
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'autoinspect_app') THEN
        CREATE ROLE autoinspect_app WITH
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            NOBYPASSRLS
            LOGIN
            PASSWORD '<REPLACE_WITH_STRONG_256BIT_PASSWORD>';
    ELSE
        ALTER ROLE autoinspect_app WITH
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            NOBYPASSRLS
            LOGIN
            PASSWORD '<REPLACE_WITH_STRONG_256BIT_PASSWORD>';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'autoinspect_app'
          AND (
              rolsuper
              OR rolreplication
              OR rolbypassrls
              OR rolcreatedb
              OR rolcreaterole
              OR rolinherit
              OR NOT rolcanlogin
          )
    ) THEN
        RAISE EXCEPTION 'autoinspect_app failed least-privilege pg_roles assertion!';
    END IF;
END $$;

-- -----------------------------------------------------------------------------
-- PART B: TARGET DATABASE MINIMAL SCHEMA, TABLE, SEQUENCE & FUNCTION GRANTS
-- Based on backend code audit (app/main.py, app/crud/*, app/routers/*):
--   - public schema      : USAGE only (CREATE explicitly revoked from PUBLIC & app role)
--   - public.users       : SELECT, INSERT (register, login, get_current_user)
--   - public.users_id_seq: USAGE, SELECT  (user registration ID allocation)
--   - public.vehicles    : SELECT, INSERT, UPDATE, DELETE (vehicle CRUD)
--   - public.inspections : SELECT, INSERT (read/create inspections; FK cascade
--                          on vehicle delete runs as table owner `postgres`)
--   - public functions   : Zero EXECUTE for PUBLIC & autoinspect_app
--                          (preserving existing service_role/authenticated/anon grants)
-- All other tables (profiles, damage_detections, detected_damages, detections,
-- reports, regions, id, *_backup_*, *_checkpoint_*) receive ZERO grants.
-- -----------------------------------------------------------------------------
BEGIN;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM autoinspect_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM autoinspect_app;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM autoinspect_app;
REVOKE ALL ON SCHEMA public FROM autoinspect_app;

-- Ensure PUBLIC does not retain CREATE on schema public or default EXECUTE on
-- sensitive public trigger/auth helper functions (roles inheriting PUBLIC such
-- as autoinspect_app would otherwise inherit PUBLIC EXECUTE).
-- Explicit grants to service_role / authenticated / anon are preserved untouched.
DO $$
DECLARE
    fn_rec RECORD;
BEGIN
    BEGIN
        REVOKE CREATE ON SCHEMA public FROM PUBLIC;
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'Could not REVOKE CREATE ON SCHEMA public FROM PUBLIC (insufficient privilege; verify manual schema ACL).';
    END;

    FOR fn_rec IN
        SELECT p.proname,
               pg_catalog.pg_get_function_identity_arguments(p.oid) AS fn_args
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND NOT EXISTS (
              SELECT 1 FROM pg_depend d
              WHERE d.objid = p.oid AND d.deptype = 'e'
          )
    LOOP
        BEGIN
            EXECUTE format('REVOKE ALL ON FUNCTION public.%I(%s) FROM PUBLIC;', fn_rec.proname, fn_rec.fn_args);
            EXECUTE format('REVOKE ALL ON FUNCTION public.%I(%s) FROM autoinspect_app;', fn_rec.proname, fn_rec.fn_args);
        EXCEPTION WHEN insufficient_privilege THEN
            RAISE NOTICE 'Could not revoke function privileges on public.%(%) (insufficient privilege).', fn_rec.proname, fn_rec.fn_args;
        END;
    END LOOP;
END $$;

GRANT USAGE ON SCHEMA public TO autoinspect_app;

GRANT SELECT, INSERT ON TABLE public.users TO autoinspect_app;
GRANT USAGE, SELECT ON SEQUENCE public.users_id_seq TO autoinspect_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.vehicles TO autoinspect_app;
GRANT SELECT, INSERT ON TABLE public.inspections TO autoinspect_app;

-- -----------------------------------------------------------------------------
-- PART C: SCOPED ROW LEVEL SECURITY (RLS) POLICIES FOR `autoinspect_app`
-- Because `autoinspect_app` has NOBYPASSRLS and all public tables have RLS
-- enabled, default-deny blocks all rows unless a policy matches `autoinspect_app`.
-- These policies are scoped strictly TO `autoinspect_app` (not `anon` or
-- `authenticated`, which remain blocked) while FastAPI enforces tenant
-- ownership (`user_id == current_user.id`) and admin RBAC at the API/CRUD layer.
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "autoinspect_app_select_users" ON public.users;
DROP POLICY IF EXISTS "autoinspect_app_insert_users" ON public.users;
CREATE POLICY "autoinspect_app_select_users"
    ON public.users AS PERMISSIVE FOR SELECT TO autoinspect_app USING (true);
CREATE POLICY "autoinspect_app_insert_users"
    ON public.users AS PERMISSIVE FOR INSERT TO autoinspect_app WITH CHECK (true);

DROP POLICY IF EXISTS "autoinspect_app_select_vehicles" ON public.vehicles;
DROP POLICY IF EXISTS "autoinspect_app_insert_vehicles" ON public.vehicles;
DROP POLICY IF EXISTS "autoinspect_app_update_vehicles" ON public.vehicles;
DROP POLICY IF EXISTS "autoinspect_app_delete_vehicles" ON public.vehicles;
CREATE POLICY "autoinspect_app_select_vehicles"
    ON public.vehicles AS PERMISSIVE FOR SELECT TO autoinspect_app USING (true);
CREATE POLICY "autoinspect_app_insert_vehicles"
    ON public.vehicles AS PERMISSIVE FOR INSERT TO autoinspect_app WITH CHECK (true);
CREATE POLICY "autoinspect_app_update_vehicles"
    ON public.vehicles AS PERMISSIVE FOR UPDATE TO autoinspect_app USING (true) WITH CHECK (true);
CREATE POLICY "autoinspect_app_delete_vehicles"
    ON public.vehicles AS PERMISSIVE FOR DELETE TO autoinspect_app USING (true);

DROP POLICY IF EXISTS "autoinspect_app_select_inspections" ON public.inspections;
DROP POLICY IF EXISTS "autoinspect_app_insert_inspections" ON public.inspections;
CREATE POLICY "autoinspect_app_select_inspections"
    ON public.inspections AS PERMISSIVE FOR SELECT TO autoinspect_app USING (true);
CREATE POLICY "autoinspect_app_insert_inspections"
    ON public.inspections AS PERMISSIVE FOR INSERT TO autoinspect_app WITH CHECK (true);

COMMIT;
