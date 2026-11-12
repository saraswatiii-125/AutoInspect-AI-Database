-- ==========================================================================
-- AUTOINSPECT AI - DDL SCHEMA DEFINITION
-- Extracted from live production PostgreSQL for test database restoration
-- ==========================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE SEQUENCE IF NOT EXISTS public."detected_damages_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."detections_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."inspections_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."reports_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."users_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."vehicles_id_seq";

CREATE TABLE IF NOT EXISTS public."users" (
    "id" INTEGER DEFAULT nextval('users_id_seq'::regclass) NOT NULL,
    "email" VARCHAR(255) NOT NULL,
    "hashed_password" VARCHAR(255) NOT NULL,
    "role" VARCHAR(50) DEFAULT 'customer'::character varying NOT NULL,
    "created_at" TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS public."profiles" (
    "id" UUID NOT NULL,
    "email" TEXT NOT NULL,
    "full_name" TEXT NULL,
    "role" TEXT DEFAULT 'customer'::text NOT NULL,
    "created_at" TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    "updated_at" TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS public."vehicles" (
    "id" TEXT NOT NULL,
    "user_id" INTEGER NULL,
    "make" VARCHAR(100) NOT NULL,
    "model" VARCHAR(100) NOT NULL,
    "year" INTEGER NOT NULL,
    "created_at" TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NULL,
    "code" TEXT NULL,
    "registration" TEXT NOT NULL,
    "color" TEXT DEFAULT 'Alpine White'::text NOT NULL,
    "image_url" TEXT NULL,
    "image" TEXT NOT NULL,
    "health_score" INTEGER DEFAULT 100 NULL,
    "latest_inspection_date" TEXT NULL,
    "updated_at" TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NULL,
    "owner_id" UUID NULL
);

CREATE TABLE IF NOT EXISTS public."inspections" (
    "id" TEXT NOT NULL,
    "vehicle_id" TEXT NULL,
    "user_id" INTEGER NULL,
    "estimated_cost_min" DOUBLE PRECISION NULL,
    "estimated_cost_max" DOUBLE PRECISION NULL,
    "created_at" TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NULL,
    "inspection_id" TEXT NULL,
    "filename" TEXT NULL,
    "detection_count" INTEGER DEFAULT 0 NULL,
    "annotated_image_url" TEXT NULL,
    "original_image_url" TEXT NULL,
    "status" TEXT DEFAULT 'completed'::text NULL,
    "overall_score" INTEGER DEFAULT 80 NULL,
    "note" TEXT NULL,
    "updated_at" TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NULL,
    "image_path" TEXT NULL,
    "image_name" TEXT NULL,
    "date" TEXT NOT NULL,
    "total_cost_min" INTEGER DEFAULT 0 NULL,
    "total_cost_max" INTEGER DEFAULT 0 NULL,
    "damages" JSONB DEFAULT '[]'::jsonb NULL,
    "images" JSONB DEFAULT '[]'::jsonb NULL,
    "ai_insights" JSONB DEFAULT '[]'::jsonb NULL
);

CREATE TABLE IF NOT EXISTS public."damage_detections" (
    "id" UUID DEFAULT gen_random_uuid() NOT NULL,
    "inspection_id" TEXT NOT NULL,
    "class_id" INTEGER NOT NULL,
    "class_name" TEXT NOT NULL,
    "confidence" NUMERIC NOT NULL,
    "box_x1" NUMERIC NOT NULL,
    "box_y1" NUMERIC NOT NULL,
    "box_x2" NUMERIC NOT NULL,
    "box_y2" NUMERIC NOT NULL,
    "created_at" TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public."detected_damages" (
    "id" INTEGER DEFAULT nextval('detected_damages_id_seq'::regclass) NOT NULL,
    "inspection_id" TEXT NULL,
    "image_url" VARCHAR(255) NULL,
    "damage_type" VARCHAR(100) NULL,
    "severity" VARCHAR(50) NULL,
    "confidence_score" DOUBLE PRECISION NULL,
    "bbox_coordinates" TEXT NULL,
    "repair_recommendation" TEXT NULL,
    "class_id" INTEGER NULL,
    "class_name" TEXT NULL,
    "confidence" NUMERIC NULL,
    "box_x1" NUMERIC NULL,
    "box_y1" NUMERIC NULL,
    "box_x2" NUMERIC NULL,
    "box_y2" NUMERIC NULL,
    "created_at" TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NULL,
    "x_min" NUMERIC NULL,
    "ymin" NUMERIC NULL,
    "x_max" NUMERIC NULL,
    "ymax" NUMERIC NULL
);

CREATE TABLE IF NOT EXISTS public."detections" (
    "id" INTEGER DEFAULT nextval('detections_id_seq'::regclass) NOT NULL,
    "inspection_id" TEXT NULL,
    "image_url" VARCHAR(255) NULL,
    "damage_type" VARCHAR(100) NULL,
    "severity" VARCHAR(50) NULL,
    "confidence_score" DOUBLE PRECISION NULL,
    "bbox_coordinates" TEXT NULL,
    "repair_recommendation" TEXT NULL,
    "class_id" INTEGER NULL,
    "class_name" TEXT NULL,
    "confidence" NUMERIC NULL,
    "box_x1" NUMERIC NULL,
    "box_y1" NUMERIC NULL,
    "box_x2" NUMERIC NULL,
    "box_y2" NUMERIC NULL,
    "created_at" TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NULL
);

CREATE TABLE IF NOT EXISTS public."reports" (
    "id" INTEGER DEFAULT nextval('reports_id_seq'::regclass) NOT NULL,
    "inspection_id" TEXT NULL,
    "pdf_report_path" VARCHAR(255) NOT NULL,
    "generated_at" TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS public."regions" (
    "id" JSONB NOT NULL,
    "created_at" TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    "inspection_id" BIGINT NULL
);

ALTER TABLE ONLY public."damage_detections" ADD CONSTRAINT "damage_detections_pkey" PRIMARY KEY ("id");
ALTER TABLE ONLY public."detected_damages" ADD CONSTRAINT "detected_damages_pkey" PRIMARY KEY ("id");
ALTER TABLE ONLY public."detections" ADD CONSTRAINT "detections_pkey" PRIMARY KEY ("id");
ALTER TABLE ONLY public."inspections" ADD CONSTRAINT "inspections_pkey" PRIMARY KEY ("id");
ALTER TABLE ONLY public."profiles" ADD CONSTRAINT "profiles_pkey" PRIMARY KEY ("id");
ALTER TABLE ONLY public."regions" ADD CONSTRAINT "regions_pkey" PRIMARY KEY ("id");
ALTER TABLE ONLY public."reports" ADD CONSTRAINT "reports_pkey" PRIMARY KEY ("id");
ALTER TABLE ONLY public."users" ADD CONSTRAINT "users_pkey" PRIMARY KEY ("id");
ALTER TABLE ONLY public."vehicles" ADD CONSTRAINT "vehicles_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY public."inspections" ADD CONSTRAINT "inspections_inspection_id_key" UNIQUE ("inspection_id");
ALTER TABLE ONLY public."users" ADD CONSTRAINT "users_email_key" UNIQUE ("email");
ALTER TABLE ONLY public."vehicles" ADD CONSTRAINT "vehicles_registration_key" UNIQUE ("registration");

ALTER TABLE ONLY public."damage_detections" ADD CONSTRAINT "damage_detections_confidence_check" CHECK (((confidence >= (0)::numeric) AND (confidence <= (1)::numeric)));
ALTER TABLE ONLY public."inspections" ADD CONSTRAINT "inspections_vehicle_id_required" CHECK ((vehicle_id IS NOT NULL)) NOT VALID;
ALTER TABLE ONLY public."profiles" ADD CONSTRAINT "profiles_role_check" CHECK ((role = ANY (ARRAY['customer'::text, 'admin'::text])));

ALTER TABLE ONLY public."damage_detections" ADD CONSTRAINT "damage_detections_inspection_id_fkey" FOREIGN KEY ("inspection_id") REFERENCES public."inspections" ("inspection_id") ON DELETE CASCADE ON UPDATE NO ACTION;
ALTER TABLE ONLY public."detected_damages" ADD CONSTRAINT "detected_damages_inspection_id_fkey" FOREIGN KEY ("inspection_id") REFERENCES public."inspections" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;
ALTER TABLE ONLY public."detections" ADD CONSTRAINT "detections_inspection_id_fkey" FOREIGN KEY ("inspection_id") REFERENCES public."inspections" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;
ALTER TABLE ONLY public."inspections" ADD CONSTRAINT "inspections_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES public."users" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;
ALTER TABLE ONLY public."inspections" ADD CONSTRAINT "inspections_vehicle_id_fkey" FOREIGN KEY ("vehicle_id") REFERENCES public."vehicles" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;
ALTER TABLE ONLY public."reports" ADD CONSTRAINT "reports_inspection_id_fkey" FOREIGN KEY ("inspection_id") REFERENCES public."inspections" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;
ALTER TABLE ONLY public."vehicles" ADD CONSTRAINT "vehicles_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES public."profiles" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE ONLY public."vehicles" ADD CONSTRAINT "vehicles_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES public."users" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;

CREATE INDEX idx_damage_detections_inspection_id ON public.damage_detections USING btree (inspection_id);
CREATE INDEX idx_detected_damages_inspection_id ON public.detected_damages USING btree (inspection_id);
CREATE INDEX idx_detections_inspection_id ON public.detections USING btree (inspection_id);
CREATE INDEX idx_inspections_created_at ON public.inspections USING btree (created_at DESC);
CREATE INDEX idx_inspections_user_id ON public.inspections USING btree (user_id);
CREATE INDEX idx_inspections_vehicle_id ON public.inspections USING btree (vehicle_id);
CREATE INDEX idx_reports_inspection_id ON public.reports USING btree (inspection_id);
CREATE INDEX idx_vehicles_owner_id ON public.vehicles USING btree (owner_id);
CREATE INDEX idx_vehicles_user_id ON public.vehicles USING btree (user_id);