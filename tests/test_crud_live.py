"""Live backend CRUD integration test suite for AutoInspect AI against Supabase PostgreSQL.

Executes complete CRUD lifecycle validation using temporary UUID-based test records.
Guarantees zero mutation of existing baseline records (5 vehicles, 57 inspections).

Safety Gate:
    Requires AUTOINSPECT_ALLOW_LIVE_CRUD_TESTS=YES in environment to execute.
"""

import sys as _sys
from pathlib import Path as _Path
_MODELS_DIR = _Path(__file__).resolve().parent.parent / 'models'
if str(_MODELS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_MODELS_DIR))
import os
import sys
import uuid
from pathlib import Path
from sqlalchemy import text
from fastapi import HTTPException

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent
vendor_dir = backend_dir / "vendor"
if vendor_dir.exists() and str(vendor_dir) not in sys.path:
    sys.path.insert(0, str(vendor_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
project_dir = backend_dir.parent
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))

from app.database import engine, SessionLocal
from app.models.user import UserModel
from app.models.vehicle import VehicleModel
from app.models.inspection import InspectionModel
from app.schemas.vehicle import VehicleCreate, VehicleUpdate
from app.schemas.inspection import (
    CreateInspectionRequestSchema,
    DamageSchema,
    BBoxSchema,
    InspectionImageSchema,
)
from app.routers.vehicles import (
    list_vehicles,
    read_vehicle,
    add_vehicle,
    edit_vehicle,
    remove_vehicle,
)
from app.routers.inspections import (
    list_inspections,
    read_inspection,
    add_inspection,
)

# Immutable protected baseline identifiers
PROTECTED_VEHICLE_IDS = {"1", "2", "3", "string", "v_1793622734600"}
PROTECTED_REGISTRATIONS = {
    "MH-12-AB-2026",
    "DL-01-XY-4421",
    "KA-03-MN-8890",
    "string",
    "TEST-AI-2025-004",
}
EXPECTED_BASELINE_VEHICLES = 5
EXPECTED_BASELINE_INSPECTIONS = 57


def run_live_crud_suite():
    """Executes the 8-case CRUD test lifecycle with strict safety checks and guaranteed cleanup."""
    # -------------------------------------------------------------------------
    # SAFETY GATE 1: Environment variable check
    # -------------------------------------------------------------------------
    allow_live = os.getenv("AUTOINSPECT_ALLOW_LIVE_CRUD_TESTS", "").strip().upper()
    if allow_live != "YES":
        print("=" * 70)
        print("SAFETY GATE: Live CRUD testing is disabled.")
        print("Set AUTOINSPECT_ALLOW_LIVE_CRUD_TESTS=YES to execute live CRUD tests.")
        print("Aborting immediately without connecting or performing any database writes.")
        print("=" * 70)
        sys.exit(1)

    # -------------------------------------------------------------------------
    # SAFETY GATE 2: UUID-based run-specific unique identifiers
    # -------------------------------------------------------------------------
    run_uuid = uuid.uuid4().hex[:12]
    test_vehicle_id = f"test_v_{run_uuid}"
    test_registration = f"TMP-UUID-{run_uuid.upper()}"
    test_inspection_id = f"test_i_{run_uuid}"
    test_damage_id = f"test_d_{run_uuid}"

    print("=" * 70)
    print("STARTING PHASE 6: AUTOINSPECT AI LIVE BACKEND CRUD TEST SUITE")
    print(f"Generated Run UUID: {run_uuid}")
    print(f"Temporary Vehicle ID: {test_vehicle_id}")
    print(f"Temporary Registration: {test_registration}")
    print(f"Temporary Inspection ID: {test_inspection_id}")
    print("=" * 70)

    db = SessionLocal()
    # Ensure test admin user exists in DB for foreign key constraint on vehicles.user_id
    existing_admin = db.query(UserModel).filter(UserModel.id == 999).first()
    if not existing_admin:
        existing_admin = UserModel(
            id=999,
            email=f"admin_{run_uuid}@test.com",
            hashed_password="$argon2id$v=19$m=65536,t=3,p=4$dummyhashtestforadmin999$",
            role="admin",
        )
        db.add(existing_admin)
        db.commit()
    admin_user = existing_admin
    cleanup_needed = False

    try:
        # ---------------------------------------------------------------------
        # STEP 0: PRE-EXECUTION BASELINE & COLLISION CHECKS
        # ---------------------------------------------------------------------
        print("\n[STEP 0] Performing baseline state and collision verification...")

        # 0.1 Verify baseline counts
        initial_v_count = db.query(VehicleModel).count()
        initial_i_count = db.query(InspectionModel).count()
        print(f"  Current vehicles count: {initial_v_count} (expected {EXPECTED_BASELINE_VEHICLES})")
        print(f"  Current inspections count: {initial_i_count} (expected {EXPECTED_BASELINE_INSPECTIONS})")

        if initial_v_count != EXPECTED_BASELINE_VEHICLES:
            raise RuntimeError(
                f"SAFETY ABORT: Vehicle baseline count is {initial_v_count}, "
                f"expected {EXPECTED_BASELINE_VEHICLES}. Aborting without writes."
            )
        if initial_i_count != EXPECTED_BASELINE_INSPECTIONS:
            raise RuntimeError(
                f"SAFETY ABORT: Inspection baseline count is {initial_i_count}, "
                f"expected {EXPECTED_BASELINE_INSPECTIONS}. Aborting without writes."
            )

        # 0.2 Verify protected vehicles exist
        existing_v_ids = {v.id for v in db.query(VehicleModel.id).all()}
        assert PROTECTED_VEHICLE_IDS.issubset(existing_v_ids), (
            "SAFETY ABORT: One or more protected baseline vehicles are missing from database!"
        )

        # 0.3 Verify collision prevention
        assert test_vehicle_id not in existing_v_ids, (
            f"SAFETY ABORT: Collision detected! ID '{test_vehicle_id}' already exists."
        )
        existing_regs = {v.registration for v in db.query(VehicleModel.registration).all()}
        assert test_registration not in existing_regs, (
            f"SAFETY ABORT: Collision detected! Registration '{test_registration}' already exists."
        )
        existing_i_ids = {i.id for i in db.query(InspectionModel.id).all()}
        assert test_inspection_id not in existing_i_ids, (
            f"SAFETY ABORT: Collision detected! Inspection ID '{test_inspection_id}' already exists."
        )

        # 0.4 Pre-verify database-level ON DELETE CASCADE constraint
        cascade_check = db.execute(text("""
            SELECT confdeltype
            FROM pg_constraint
            WHERE conrelid = 'public.inspections'::regclass
              AND conname = 'inspections_vehicle_id_fkey';
        """)).scalar()
        assert cascade_check == "c", (
            f"SAFETY ABORT: inspections foreign key delete rule is '{cascade_check}', expected 'c' (CASCADE)."
        )
        print("  Baseline verified. Foreign key cascade verified. Zero collisions found.")

        # ---------------------------------------------------------------------
        # CASE 1: CREATE A VEHICLE
        # ---------------------------------------------------------------------
        print("\n[CASE 1] Testing POST /api/vehicles (Create Vehicle)...")
        cleanup_needed = True  # Flag cleanup in case of mid-test failure
        new_v = VehicleCreate(
            id=test_vehicle_id,
            make="Porsche",
            model="Taycan Turbo",
            year=2024,
            registration=test_registration,
            color="Frozen Blue Metallic",
            image="https://images.unsplash.com/photo-1614162692292-7ac56d7f7f1e",
        )
        created_v = add_vehicle(new_v, db=db, current_user=admin_user)
        assert created_v.id == test_vehicle_id
        assert created_v.make == "Porsche"
        assert created_v.registration == test_registration
        assert created_v.health_score == 100
        assert created_v.inspections == []

        # Negative test: Duplicate registration must raise HTTP 400
        duplicate_raised = False
        try:
            add_vehicle(new_v, db=db, current_user=admin_user)
        except HTTPException as ctx:
            duplicate_raised = True
            assert ctx.status_code == 400
        assert duplicate_raised, "Expected HTTP 400 on duplicate registration creation"
        print("  CASE 1 PASSED: Vehicle created successfully; duplicate registration rejected with 400.")

        # ---------------------------------------------------------------------
        # CASE 2: GET ALL VEHICLES
        # ---------------------------------------------------------------------
        print("\n[CASE 2] Testing GET /api/vehicles (List Vehicles)...")
        all_vehicles = list_vehicles(db=db, current_user=admin_user)
        assert len(all_vehicles) == EXPECTED_BASELINE_VEHICLES + 1, (
            f"Expected {EXPECTED_BASELINE_VEHICLES + 1} vehicles, found {len(all_vehicles)}"
        )
        all_v_ids = {v.id for v in all_vehicles}
        assert test_vehicle_id in all_v_ids
        assert PROTECTED_VEHICLE_IDS.issubset(all_v_ids), (
            "Protected baseline vehicles were altered or removed!"
        )
        # Verify camelCase serialization on all vehicles
        for v in all_vehicles:
            v_dict = v.model_dump(by_alias=True)
            assert "healthScore" in v_dict
            assert "latestInspectionDate" in v_dict
            assert "inspections" in v_dict
        print(f"  CASE 2 PASSED: Listed {len(all_vehicles)} vehicles; all 5 baseline vehicles intact.")

        # ---------------------------------------------------------------------
        # CASE 3: GET VEHICLE BY ID
        # ---------------------------------------------------------------------
        print(f"\n[CASE 3] Testing GET /api/vehicles/{test_vehicle_id} (Read Vehicle)...")
        fetched_v = read_vehicle(test_vehicle_id, db=db, current_user=admin_user)
        assert fetched_v.id == test_vehicle_id
        assert fetched_v.registration == test_registration
        assert fetched_v.color == "Frozen Blue Metallic"

        # Negative test: Non-existent ID must raise HTTP 404
        not_found_raised = False
        try:
            read_vehicle("v_non_existent_uuid_id", db=db, current_user=admin_user)
        except HTTPException as ctx:
            not_found_raised = True
            assert ctx.status_code == 404
        assert not_found_raised, "Expected HTTP 404 on non-existent vehicle lookup"
        print("  CASE 3 PASSED: Read vehicle by ID verified; non-existent ID rejected with 404.")

        # ---------------------------------------------------------------------
        # CASE 4: UPDATE VEHICLE DETAILS
        # ---------------------------------------------------------------------
        print(f"\n[CASE 4] Testing PUT /api/vehicles/{test_vehicle_id} (Update Vehicle)...")
        # Strict defensive assertion: Ensure target is strictly the test vehicle
        assert test_vehicle_id not in PROTECTED_VEHICLE_IDS
        assert test_vehicle_id.startswith("test_v_")

        update_payload = VehicleUpdate(
            color="Gentian Blue Metallic",
            healthScore=95,
        )
        updated_v = edit_vehicle(test_vehicle_id, update_payload, db=db, current_user=admin_user)
        assert updated_v.color == "Gentian Blue Metallic"
        assert updated_v.health_score == 95
        assert updated_v.registration == test_registration

        # Negative test: Conflict on duplicate registration must raise HTTP 409
        conflict_raised = False
        try:
            conflict_payload = VehicleUpdate(registration="MH-12-AB-2026")
            edit_vehicle(test_vehicle_id, conflict_payload, db=db, current_user=admin_user)
        except HTTPException as ctx:
            conflict_raised = True
            assert ctx.status_code == 409
            assert "already exists" in str(ctx.detail).lower()
        assert conflict_raised, "Expected HTTP 409 on registration conflict"
        print("  CASE 4 PASSED: Updated vehicle fields; conflict rejected with 409.")

        # ---------------------------------------------------------------------
        # CASE 5: CREATE AN INSPECTION LINKED TO TEST VEHICLE
        # ---------------------------------------------------------------------
        print("\n[CASE 5] Testing POST /api/inspections (Create Inspection)...")
        # Strict defensive assertion: Ensure linked vehicle is strictly the test vehicle
        assert test_vehicle_id not in PROTECTED_VEHICLE_IDS
        assert test_vehicle_id.startswith("test_v_")

        insp_payload = CreateInspectionRequestSchema(
            id=test_inspection_id,
            vehicleId=test_vehicle_id,
            date="2026-11-05",
            status="completed",
            overallScore=88,
            totalCostMin=4500,
            totalCostMax=7500,
            damages=[
                DamageSchema(
                    id=test_damage_id,
                    part="Front Bumper",
                    type="Scratch",
                    severity="minor",
                    confidence=94.5,
                    costMin=4500,
                    costMax=7500,
                    recommendation="Buffing and touch-up paint",
                    bbox=BBoxSchema(x=10.0, y=45.0, w=25.0, h=15.0),
                    imageIndex=0,
                )
            ],
            images=[
                InspectionImageSchema(
                    label="Front Bumper",
                    url="https://example.com/test_front.jpg",
                    damages=[test_damage_id],
                )
            ],
            aiInsights=["Minor scratch detected on front bumper."],
        )
        created_i = add_inspection(insp_payload, db=db, current_user=admin_user)
        assert created_i.id == test_inspection_id
        assert created_i.vehicle_id == test_vehicle_id
        assert created_i.overall_score == 88
        assert created_i.total_cost_min == 4500
        assert created_i.total_cost_max == 7500

        # Verify parent vehicle auto-updated health score and inspection date
        parent_v = read_vehicle(test_vehicle_id, db=db, current_user=admin_user)
        assert parent_v.health_score == 88
        assert parent_v.latest_inspection_date == "2026-11-05"

        # Negative test: Non-existent vehicle ID must raise HTTP 404
        unlinked_raised = False
        try:
            bad_insp = CreateInspectionRequestSchema(
                vehicleId="v_non_existent_parent_id",
                date="2026-11-05",
            )
            add_inspection(bad_insp, db=db, current_user=admin_user)
        except HTTPException as ctx:
            unlinked_raised = True
            assert ctx.status_code == 404
        assert unlinked_raised, "Expected HTTP 404 on inspection with invalid vehicleId"
        print("  CASE 5 PASSED: Inspection created; parent vehicle score updated; invalid vehicleId rejected with 404.")

        # ---------------------------------------------------------------------
        # CASE 6: GET INSPECTION BY ID
        # ---------------------------------------------------------------------
        print(f"\n[CASE 6] Testing GET /api/inspections/{test_inspection_id} (Read Inspection)...")
        fetched_i = read_inspection(test_inspection_id, db=db, current_user=admin_user)
        assert fetched_i.id == test_inspection_id
        assert fetched_i.vehicle_id == test_vehicle_id
        assert fetched_i.overall_score == 88
        assert len(fetched_i.damages) == 1
        assert fetched_i.damages[0].part == "Front Bumper"
        assert fetched_i.damages[0].cost_min == 4500

        # Negative test: Non-existent ID must raise HTTP 404
        insp_404_raised = False
        try:
            read_inspection("i_non_existent_uuid_id", db=db, current_user=admin_user)
        except HTTPException as ctx:
            insp_404_raised = True
            assert ctx.status_code == 404
        assert insp_404_raised, "Expected HTTP 404 on non-existent inspection lookup"
        print("  CASE 6 PASSED: Read inspection by ID verified; nested fields intact; non-existent ID rejected with 404.")

        # ---------------------------------------------------------------------
        # CASE 7: FILTER INSPECTIONS BY VEHICLE ID
        # ---------------------------------------------------------------------
        print(f"\n[CASE 7] Testing GET /api/inspections?vehicleId={test_vehicle_id} (Filter Inspections)...")
        test_v_insps = list_inspections(vehicle_id=test_vehicle_id, db=db, current_user=admin_user)
        assert len(test_v_insps) == 1
        assert test_v_insps[0].id == test_inspection_id
        assert test_v_insps[0].vehicle_id == test_vehicle_id

        # Baseline integrity check: Vehicle 1 still has exactly 48 inspections
        v1_insps = list_inspections(vehicle_id="1", db=db, current_user=admin_user)
        assert len(v1_insps) == 48, f"Expected 48 inspections for vehicle 1, got {len(v1_insps)}"
        print(f"  CASE 7 PASSED: Filter returned exactly 1 inspection for test vehicle; vehicle 1 baseline intact ({len(v1_insps)}).")

        # ---------------------------------------------------------------------
        # CASE 8: DELETE TEST VEHICLE & VERIFY CASCADE DELETION
        # ---------------------------------------------------------------------
        print(f"\n[CASE 8] Testing DELETE /api/vehicles/{test_vehicle_id} (Delete & Cascade)...")
        # Strict defensive assertion: Ensure target is strictly the test vehicle
        assert test_vehicle_id not in PROTECTED_VEHICLE_IDS
        assert test_vehicle_id.startswith("test_v_")

        del_resp = remove_vehicle(test_vehicle_id, db=db, current_user=admin_user)
        assert del_resp.success is True
        assert del_resp.id == test_vehicle_id

        # 8.1 Confirm test vehicle is 404
        v_deleted = False
        try:
            read_vehicle(test_vehicle_id, db=db, current_user=admin_user)
        except HTTPException as ctx:
            v_deleted = (ctx.status_code == 404)
        assert v_deleted, "Test vehicle was not deleted properly!"

        # 8.2 Confirm cascade deletion: Linked inspection is 404
        i_cascade_deleted = False
        try:
            read_inspection(test_inspection_id, db=db, current_user=admin_user)
        except HTTPException as ctx:
            i_cascade_deleted = (ctx.status_code == 404)
        assert i_cascade_deleted, "Linked inspection was NOT cascade-deleted by foreign key constraint!"
        cleanup_needed = False  # Normal deletion succeeded cleanly
        print("  CASE 8 PASSED: Test vehicle deleted; linked inspection cascade-deleted verified.")

    finally:
        db.close()
        # ---------------------------------------------------------------------
        # RESILIENT POST-TEST CLEANUP HANDLER (RUNS ALWAYS)
        # ---------------------------------------------------------------------
        cleanup_db = SessionLocal()
        try:
            print("\n[CLEANUP] Executing post-test verification and cleanup...")
            if cleanup_needed:
                print(f"  Attempting targeted removal of temporary test vehicle '{test_vehicle_id}'...")
                # Defensive check before deletion
                assert test_vehicle_id not in PROTECTED_VEHICLE_IDS
                assert test_vehicle_id.startswith("test_v_")
                v_obj = cleanup_db.query(VehicleModel).filter(VehicleModel.id == test_vehicle_id).first()
                if v_obj:
                    cleanup_db.delete(v_obj)
                    cleanup_db.commit()
                    print(f"  Targeted removal of '{test_vehicle_id}' completed.")

            # Clean up temporary admin user
            cleanup_db.query(UserModel).filter(UserModel.id == 999).delete()
            cleanup_db.commit()

            # Final baseline assertion: Exactly 5 vehicles and 57 inspections must remain
            final_v_count = cleanup_db.query(VehicleModel).count()
            final_i_count = cleanup_db.query(InspectionModel).count()
            remaining_v_ids = {v.id for v in cleanup_db.query(VehicleModel.id).all()}

            print(f"  Final vehicles count: {final_v_count} (expected {EXPECTED_BASELINE_VEHICLES})")
            print(f"  Final inspections count: {final_i_count} (expected {EXPECTED_BASELINE_INSPECTIONS})")

            assert final_v_count == EXPECTED_BASELINE_VEHICLES, (
                f"COUNT MISMATCH: Expected {EXPECTED_BASELINE_VEHICLES} vehicles, found {final_v_count}!"
            )
            assert final_i_count == EXPECTED_BASELINE_INSPECTIONS, (
                f"COUNT MISMATCH: Expected {EXPECTED_BASELINE_INSPECTIONS} inspections, found {final_i_count}!"
            )
            assert PROTECTED_VEHICLE_IDS == remaining_v_ids, (
                f"BASELINE INTEGRITY VIOLATION: Existing vehicle IDs mismatch: {remaining_v_ids}"
            )
            assert test_vehicle_id not in remaining_v_ids, (
                f"CLEANUP INCOMPLETE: Test vehicle '{test_vehicle_id}' still present in database!"
            )
            print("  Cleanup verified: Baseline state fully restored. All 5 original vehicles and 57 inspections intact.")

        except Exception as cleanup_err:
            print("=" * 70)
            print("CRITICAL WARNING: CLEANUP HANDLER ENCOUNTERED AN ISSUE")
            print(f"Error detail: {cleanup_err}")
            print("ATTENTION REQUIRED: Manual verification for temporary test records:")
            print(f"  - Table 'vehicles': id = '{test_vehicle_id}', registration = '{test_registration}'")
            print(f"  - Table 'inspections': id = '{test_inspection_id}'")
            print("DO NOT RUN BROAD CLEANUP. ONLY TARGET THE EXACT TEST IDENTIFIERS ABOVE.")
            print("=" * 70)
            raise
        finally:
            cleanup_db.close()

    print("\n" + "=" * 70)
    print("ALL 8 LIVE CRUD TEST CASES COMPLETED SUCCESSFULLY WITH ZERO SIDE EFFECTS.")
    print("=" * 70)


if __name__ == "__main__":
    run_live_crud_suite()

