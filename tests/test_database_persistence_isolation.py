"""
Comprehensive verification test suite for AutoInspect AI:
- Phase 4: Application Data Persistence & JSON structures
- Phase 5: Customer vs Customer isolation & Admin fleet access
- Phase 6: Transaction integrity & Cascade deletion
"""

import sys as _sys
from pathlib import Path as _Path
_MODELS_DIR = _Path(__file__).resolve().parent.parent / 'models'
if str(_MODELS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_MODELS_DIR))
import uuid
from sqlalchemy import text
from fastapi import HTTPException

from app.database import SessionLocal, engine
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

RUN_ID = uuid.uuid4().hex[:8]

TEST_USER_A_ID = 1001
TEST_USER_B_ID = 1002
TEST_ADMIN_ID = 1003

VEHICLE_A_ID = f"test_v_pers_a_{RUN_ID}"
VEHICLE_B_ID = f"test_v_pers_b_{RUN_ID}"
INSPECTION_A_ID = f"test_i_pers_a_{RUN_ID}"
INSPECTION_B_ID = f"test_i_pers_b_{RUN_ID}"

REG_A = f"TMP-PERS-A-{RUN_ID.upper()}"
REG_B = f"TMP-PERS-B-{RUN_ID.upper()}"

def run_tests():
    print("=" * 75)
    print(f"RUNNING PHASES 4, 5, 6 VERIFICATION TEST SUITE (Run ID: {RUN_ID})")
    print("=" * 75)

    db = SessionLocal()

    # Pre-verification: baseline count
    baseline_v_count = db.query(VehicleModel).count()
    baseline_i_count = db.query(InspectionModel).count()
    print(f"[PRE-CHECK] Baseline vehicles: {baseline_v_count}, Baseline inspections: {baseline_i_count}")

    # Set up test users
    try:
        # Create users
        user_a = UserModel(
            id=TEST_USER_A_ID,
            email=f"cust_a_{RUN_ID}@example.com",
            hashed_password="hash",
            role="customer",
        )
        user_b = UserModel(
            id=TEST_USER_B_ID,
            email=f"cust_b_{RUN_ID}@example.com",
            hashed_password="hash",
            role="customer",
        )
        admin_user = UserModel(
            id=TEST_ADMIN_ID,
            email=f"admin_{RUN_ID}@example.com",
            hashed_password="hash",
            role="admin",
        )
        db.add_all([user_a, user_b, admin_user])
        db.commit()
        print("[SETUP] Created test users: Customer A (1001), Customer B (1002), Admin (1003)")

        # ---------------------------------------------------------------------
        # PHASE 4: APPLICATION DATA PERSISTENCE & JSON INTEGRITY
        # ---------------------------------------------------------------------
        print("\n--- PHASE 4: APPLICATION DATA PERSISTENCE VERIFICATION ---")

        v_create = VehicleCreate(
            id=VEHICLE_A_ID,
            make="BMW",
            model="M3 Competition",
            year=2024,
            registration=REG_A,
            color="Isle of Man Green",
            image="https://example.com/m3.jpg",
        )
        created_v = add_vehicle(v_create, db=db, current_user=user_a)
        assert created_v.id == VEHICLE_A_ID
        print(f"  [4.1] Vehicle {VEHICLE_A_ID} created via API for Customer A.")

        damage_item = DamageSchema(
            id=f"dmg_{RUN_ID}",
            part="Front Splitter",
            type="Crack",
            severity="moderate",
            confidence=95.8,
            costMin=15000,
            costMax=25000,
            recommendation="Replace carbon fiber splitter",
            bbox=BBoxSchema(x=15.5, y=72.0, w=30.0, h=12.5),
            imageIndex=0,
        )
        image_item = InspectionImageSchema(
            label="Front Low Angle",
            url="https://example.com/splitter.jpg",
            damages=[damage_item.id],
        )

        i_create = CreateInspectionRequestSchema(
            id=INSPECTION_A_ID,
            vehicleId=VEHICLE_A_ID,
            date="2026-11-08",
            status="completed",
            overallScore=82,
            totalCostMin=15000,
            totalCostMax=25000,
            damages=[damage_item],
            images=[image_item],
            aiInsights=["Structural carbon damage detected on lower front splitter."],
        )
        created_i = add_inspection(i_create, db=db, current_user=user_a)
        assert created_i.id == INSPECTION_A_ID
        print(f"  [4.2] Inspection {INSPECTION_A_ID} created with embedded JSON damages and images.")

        # Close session and open a fresh connection to verify raw PostgreSQL disk persistence
        db.close()
        db = SessionLocal()
        user_a = db.query(UserModel).filter(UserModel.id == TEST_USER_A_ID).first()
        user_b = db.query(UserModel).filter(UserModel.id == TEST_USER_B_ID).first()
        admin_user = db.query(UserModel).filter(UserModel.id == TEST_ADMIN_ID).first()

        with engine.connect() as raw_conn:
            raw_v = raw_conn.execute(
                text("SELECT id, user_id, make, model, year, registration, color, health_score FROM vehicles WHERE id = :id"),
                {"id": VEHICLE_A_ID},
            ).fetchone()
            assert raw_v is not None
            assert raw_v[1] == TEST_USER_A_ID
            assert raw_v[2] == "BMW"
            assert raw_v[5] == REG_A
            assert raw_v[7] == 82  # auto-updated from inspection overall_score

            raw_i = raw_conn.execute(
                text("SELECT id, vehicle_id, user_id, overall_score, total_cost_min, total_cost_max, damages, images, ai_insights FROM inspections WHERE id = :id"),
                {"id": INSPECTION_A_ID},
            ).fetchone()
            assert raw_i is not None
            assert raw_i[1] == VEHICLE_A_ID
            assert raw_i[2] == TEST_USER_A_ID
            assert raw_i[3] == 82
            assert raw_i[4] == 15000
            assert raw_i[5] == 25000

            # Verify JSON structures persisted accurately
            raw_damages = raw_i[6]
            assert isinstance(raw_damages, list)
            assert len(raw_damages) == 1
            assert raw_damages[0]["part"] == "Front Splitter"
            assert raw_damages[0]["bbox"]["x"] == 15.5

            raw_images = raw_i[7]
            assert isinstance(raw_images, list)
            assert raw_images[0]["label"] == "Front Low Angle"

            print("  [4.3] Direct PostgreSQL SQL persistence verified: types, user_id FK, and JSONB structures intact.")

        # ---------------------------------------------------------------------
        # PHASE 5: CUSTOMER VS CUSTOMER ISOLATION & ADMIN ACCESS
        # ---------------------------------------------------------------------
        print("\n--- PHASE 5: CUSTOMER VS CUSTOMER ISOLATION & ADMIN ACCESS ---")

        # 5.1 Customer B lists vehicles: Customer A's vehicle must NOT appear
        cust_b_vehicles = list_vehicles(db=db, current_user=user_b)
        cust_b_v_ids = [v.id for v in cust_b_vehicles]
        assert VEHICLE_A_ID not in cust_b_v_ids, "Customer B saw Customer A's vehicle in vehicle list!"
        print(f"  [5.1] List isolation verified: Customer B returned {len(cust_b_vehicles)} vehicles, excluding Customer A's vehicle.")

        # 5.2 Customer B tries to read Customer A's vehicle: 404 Not Found
        try:
            read_vehicle(VEHICLE_A_ID, db=db, current_user=user_b)
            assert False, "Customer B was able to read Customer A's vehicle!"
        except HTTPException as exc:
            assert exc.status_code == 404, f"Expected 404 for unauthorized vehicle read, got {exc.status_code}"
            print("  [5.2] Read isolation verified: Customer B read of Customer A's vehicle rejected with 404.")

        # 5.3 Customer B tries to update Customer A's vehicle: 404 Not Found
        try:
            edit_vehicle(VEHICLE_A_ID, VehicleUpdate(color="Hot Pink"), db=db, current_user=user_b)
            assert False, "Customer B was able to update Customer A's vehicle!"
        except HTTPException as exc:
            assert exc.status_code == 404, f"Expected 404 for unauthorized vehicle edit, got {exc.status_code}"
            print("  [5.3] Update isolation verified: Customer B update of Customer A's vehicle rejected with 404.")

        # 5.4 Customer B tries to delete Customer A's vehicle: 404 Not Found
        try:
            remove_vehicle(VEHICLE_A_ID, db=db, current_user=user_b)
            assert False, "Customer B was able to delete Customer A's vehicle!"
        except HTTPException as exc:
            assert exc.status_code == 404, f"Expected 404 for unauthorized vehicle delete, got {exc.status_code}"
            print("  [5.4] Delete isolation verified: Customer B delete of Customer A's vehicle rejected with 404.")

        # 5.5 Customer B tries to read Customer A's inspection: 404 Not Found
        try:
            read_inspection(INSPECTION_A_ID, db=db, current_user=user_b)
            assert False, "Customer B was able to read Customer A's inspection!"
        except HTTPException as exc:
            assert exc.status_code == 404, f"Expected 404 for unauthorized inspection read, got {exc.status_code}"
            print("  [5.5] Inspection read isolation verified: Customer B read of Customer A's inspection rejected with 404.")

        # 5.6 Customer B lists inspections: Customer A's inspection must NOT appear
        cust_b_inspections = list_inspections(db=db, current_user=user_b)
        cust_b_i_ids = [i.id for i in cust_b_inspections]
        assert INSPECTION_A_ID not in cust_b_i_ids, "Customer B saw Customer A's inspection in list!"
        print(f"  [5.6] Inspection list isolation verified: Customer B returned {len(cust_b_inspections)} inspections, excluding Customer A's inspection.")

        # 5.7 Admin access: Admin CAN read Customer A's vehicle and inspection
        admin_v = read_vehicle(VEHICLE_A_ID, db=db, current_user=admin_user)
        assert admin_v.id == VEHICLE_A_ID
        admin_i = read_inspection(INSPECTION_A_ID, db=db, current_user=admin_user)
        assert admin_i.id == INSPECTION_A_ID
        print("  [5.7] Admin fleet access verified: Admin successfully accessed Customer A's vehicle and inspection.")

        # ---------------------------------------------------------------------
        # PHASE 6: TRANSACTION INTEGRITY & CASCADE DELETION
        # ---------------------------------------------------------------------
        print("\n--- PHASE 6: TRANSACTION INTEGRITY & CASCADE DELETION ---")

        # 6.1 Transaction Rollback Verification
        try:
            with db.begin_nested():
                # Attempt to insert an inspection pointing to a non-existent vehicle
                bad_insp = InspectionModel(
                    id=f"test_rollback_{RUN_ID}",
                    vehicle_id="v_non_existent_foreign_key_target",
                    date="2026-11-08",
                    overall_score=50,
                )
                db.add(bad_insp)
                db.flush()
        except Exception:
            db.rollback()
            print("  [6.1] Transaction rollback verified: Database constraint violation properly rolled back transaction.")

        # Ensure no dirty state from rollback
        rolled_back_row = db.query(InspectionModel).filter(InspectionModel.id == f"test_rollback_{RUN_ID}").first()
        assert rolled_back_row is None, "Rollback failed! Orphan record found."

        # 6.2 Deletion & Database ON DELETE CASCADE Verification
        del_resp = remove_vehicle(VEHICLE_A_ID, db=db, current_user=admin_user)
        assert del_resp.success is True
        print(f"  [6.2] Parent vehicle {VEHICLE_A_ID} deleted.")

        # Confirm vehicle is gone
        v_after_del = db.query(VehicleModel).filter(VehicleModel.id == VEHICLE_A_ID).first()
        assert v_after_del is None, "Vehicle was not deleted!"

        # Confirm child inspection was deleted via database cascade
        i_after_del = db.query(InspectionModel).filter(InspectionModel.id == INSPECTION_A_ID).first()
        assert i_after_del is None, "Inspection was not cascade-deleted!"
        print("  [6.3] Database-level ON DELETE CASCADE verified: Linked inspection automatically deleted.")

    finally:
        # Guaranteed cleanup
        print("\n[CLEANUP] Cleaning up all test records and users...")
        db.rollback()
        # Clean up any leftover test vehicles
        db.query(VehicleModel).filter(VehicleModel.id.in_([VEHICLE_A_ID, VEHICLE_B_ID])).delete(synchronize_session=False)
        # Clean up any leftover test inspections
        db.query(InspectionModel).filter(InspectionModel.id.in_([INSPECTION_A_ID, INSPECTION_B_ID])).delete(synchronize_session=False)
        # Clean up test users
        db.query(UserModel).filter(UserModel.id.in_([TEST_USER_A_ID, TEST_USER_B_ID, TEST_ADMIN_ID])).delete(synchronize_session=False)
        db.commit()

        # Final assertion: exactly baseline counts remain
        final_v_count = db.query(VehicleModel).count()
        final_i_count = db.query(InspectionModel).count()
        print(f"[CLEANUP CHECK] Final vehicles: {final_v_count} (expected {baseline_v_count})")
        print(f"[CLEANUP CHECK] Final inspections: {final_i_count} (expected {baseline_i_count})")
        assert final_v_count == baseline_v_count, f"Vehicle baseline count altered! {final_v_count} vs {baseline_v_count}"
        assert final_i_count == baseline_i_count, f"Inspection baseline count altered! {final_i_count} vs {baseline_i_count}"
        db.close()

    print("\n" + "=" * 75)
    print("PHASES 4, 5, 6 INTEGRATION & ISOLATION VERIFICATION PASSED (100% SUCCESS)")
    print("=" * 75)

if __name__ == "__main__":
    run_tests()
