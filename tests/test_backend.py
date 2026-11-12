"""Automated backend test suite verifying FastAPI router endpoints, Pydantic schemas, and database cascade deletion."""

import sys as _sys
from pathlib import Path as _Path
_MODELS_DIR = _Path(__file__).resolve().parent.parent / 'models'
if str(_MODELS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_MODELS_DIR))
import os
import sys
import unittest
from pathlib import Path

# Setup paths for backend and vendor imports
backend_dir = Path(__file__).resolve().parent
vendor_dir = backend_dir / "vendor"
if vendor_dir.exists() and str(vendor_dir) not in sys.path:
    sys.path.insert(0, str(vendor_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
project_dir = backend_dir.parent
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))

# Database connection is configured via PostgreSQL environment variables (no SQLite fallback)

from sqlalchemy import text
from app.database import engine, Base, SessionLocal
from app.models.user import UserModel
_BACKUP_DIR = _Path(__file__).resolve().parent.parent / 'backup-recovery'
if str(_BACKUP_DIR) not in _sys.path:
    _sys.path.insert(0, str(_BACKUP_DIR))
from seed import seed_database
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
from app.schemas.vehicle import VehicleCreate, VehicleUpdate
from app.schemas.inspection import (
    CreateInspectionRequestSchema,
    InspectionResponse,
    DamageSchema,
    BBoxSchema,
    InspectionImageSchema,
)
from fastapi import HTTPException

class BackendTestSuite(unittest.TestCase):
    db_available = False

    @classmethod
    def setUpClass(cls):
        # Attempt connection to PostgreSQL; if unreachable in current environment, gracefully mark unavailable
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            cls.db_available = True
            Base.metadata.create_all(bind=engine)
            seed_database()
            # Ensure test admin user exists in DB for foreign key constraint
            with SessionLocal() as db:
                admin = db.query(UserModel).filter(UserModel.id == 999).first()
                if not admin:
                    admin = UserModel(
                        id=999,
                        email="admin_backend_test@autoinspect.ai",
                        hashed_password="$argon2id$v=19$m=65536,t=3,p=4$dummyhashtestforadmin999$",
                        role="admin",
                    )
                    db.add(admin)
                    db.commit()
        except Exception:
            cls.db_available = False

    @classmethod
    def tearDownClass(cls):
        if cls.db_available:
            try:
                with SessionLocal() as db:
                    db.query(UserModel).filter(UserModel.id == 999).delete()
                    db.commit()
            except Exception:
                pass

    def setUp(self):
        self.admin_user = UserModel(id=999, email="admin@autoinspect.ai", role="admin")
        if self.db_available:
            self.db = SessionLocal()
        else:
            self.db = None

    def tearDown(self):
        if self.db:
            self.db.close()

    def test_01_database_seed_and_camel_case_keys(self):
        if not self.db_available:
            self.skipTest("Database is not reachable in current environment")
        vehicles = list_vehicles(db=self.db, current_user=self.admin_user)
        self.assertGreaterEqual(len(vehicles), 3)

        # Find BMW vehicle
        bmw = next((v for v in vehicles if v.make == "BMW"), None)
        self.assertIsNotNone(bmw)
        self.assertEqual(bmw.make, "BMW")
        self.assertIn(bmw.registration, ["MH-12-AB-2026"])

        # Verify JSON dump uses exact camelCase keys for frontend contract
        bmw_dict = bmw.model_dump(by_alias=True)
        self.assertIn("healthScore", bmw_dict)
        self.assertIn("latestInspectionDate", bmw_dict)
        self.assertIn("inspections", bmw_dict)
        self.assertIn("registration", bmw_dict)

    def test_02_get_vehicle_by_id(self):
        if not self.db_available:
            self.skipTest("Database is not reachable in current environment")
        vehicles = list_vehicles(db=self.db, current_user=self.admin_user)
        target_v = vehicles[0]
        v = read_vehicle(target_v.id, db=self.db, current_user=self.admin_user)
        self.assertEqual(v.id, target_v.id)
        self.assertEqual(v.make, target_v.make)

        # 404 on nonexistent vehicle
        with self.assertRaises(HTTPException) as ctx:
            read_vehicle("nonexistent_id", db=self.db, current_user=self.admin_user)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_03_create_and_update_vehicle(self):
        if not self.db_available:
            self.skipTest("Database is not reachable in current environment")
        # Create
        new_v = VehicleCreate(
            make="Audi",
            model="A6",
            year=2023,
            registration="MH-01-TEST-9999",
            color="Mythos Black",
            image="https://images.unsplash.com/photo-1549399542-7e3f8b79c341",
        )
        created = add_vehicle(new_v, db=self.db, current_user=self.admin_user)
        self.assertEqual(created.make, "Audi")
        self.assertEqual(created.health_score, 100)
        self.assertEqual(created.inspections, [])
        created_id = created.id

        # Duplicate registration raises 400
        with self.assertRaises(HTTPException) as ctx:
            add_vehicle(new_v, db=self.db, current_user=self.admin_user)
        self.assertEqual(ctx.exception.status_code, 400)

        # Successful update of vehicle fields
        update_in = VehicleUpdate(
            color="Daytona Grey",
            healthScore=95,
        )
        updated = edit_vehicle(created_id, update_in, db=self.db, current_user=self.admin_user)
        self.assertEqual(updated.color, "Daytona Grey")
        self.assertEqual(updated.health_score, 95)

        # Successful update with a valid new unique registration
        reg_update = VehicleUpdate(registration="MH-01-TEST-8888")
        updated_reg = edit_vehicle(created_id, reg_update, db=self.db, current_user=self.admin_user)
        self.assertEqual(updated_reg.registration, "MH-01-TEST-8888")

        # Successful update retaining the vehicle's own registration
        self_reg_update = VehicleUpdate(registration="MH-01-TEST-8888", color="Nardo Grey")
        updated_self = edit_vehicle(created_id, self_reg_update, db=self.db, current_user=self.admin_user)
        self.assertEqual(updated_self.color, "Nardo Grey")

        # Duplicate registration conflict with another vehicle (v1: MH-12-AB-2026) raises 409 Conflict
        duplicate_update = VehicleUpdate(registration="MH-12-AB-2026")
        with self.assertRaises(HTTPException) as ctx:
            edit_vehicle(created_id, duplicate_update, db=self.db, current_user=self.admin_user)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Registration number already exists", str(ctx.exception.detail))

        # Clean up created vehicle so test is idempotent and does not pollute the persistent database
        try:
            remove_vehicle(created_id, db=self.db, current_user=self.admin_user)
        except Exception:
            pass

    def test_04_inspections_history_and_filtering(self):
        if not self.db_available:
            self.skipTest("Database is not reachable in current environment")
        inspections = list_inspections(db=self.db, current_user=self.admin_user)
        self.assertGreaterEqual(len(inspections), 1)

        # Inspect first inspection
        i1 = inspections[0]
        self.assertIsNotNone(i1)
        self.assertIsNotNone(i1.id)

        # Verify camelCase serialization of nested fields
        i1_dict = i1.model_dump(by_alias=True)
        self.assertIn("vehicleId", i1_dict)
        self.assertIn("overallScore", i1_dict)
        self.assertIn("totalCostMin", i1_dict)
        self.assertIn("totalCostMax", i1_dict)
        self.assertIn("aiInsights", i1_dict)
        self.assertIn("damages", i1_dict)
        self.assertIn("images", i1_dict)

        # Filter by vehicleId if vehicle_id is set
        vehicle_with_insp = next((i.vehicle_id for i in inspections if i.vehicle_id), None)
        if vehicle_with_insp:
            v_insps = list_inspections(vehicle_id=vehicle_with_insp, db=self.db, current_user=self.admin_user)
            self.assertGreaterEqual(len(v_insps), 1)
            self.assertTrue(all(i.vehicle_id == vehicle_with_insp for i in v_insps))

    def test_05_create_inspection_and_cascade_delete(self):
        if not self.db_available:
            self.skipTest("Database is not reachable in current environment")
        # 1. Create a temporary vehicle
        temp_v = add_vehicle(
            VehicleCreate(
                make="Honda",
                model="Civic",
                year=2022,
                registration="DL-02-TEMP-1111",
                color="Radiant Red",
                image="https://images.unsplash.com/photo-1549399542-7e3f8b79c341",
            ),
            db=self.db,
            current_user=self.admin_user,
        )
        v_temp_id = temp_v.id

        # 2. Create an inspection linked to this vehicle
        insp_in = CreateInspectionRequestSchema(
            vehicleId=v_temp_id,
            date="2025-01-10",
            status="completed",
            overallScore=88,
            totalCostMin=5000,
            totalCostMax=8000,
            damages=[
                DamageSchema(
                    id="d_temp",
                    part="Rear Fender",
                    type="Scratch",
                    severity="minor",
                    confidence=93,
                    costMin=5000,
                    costMax=8000,
                    recommendation="Buff & Repaint",
                    bbox=BBoxSchema(x=10, y=20, w=15, h=25),
                    imageIndex=1,
                )
            ],
            images=[
                InspectionImageSchema(label="Front View", url="https://example.com/front.jpg", damages=[]),
                InspectionImageSchema(label="Rear View", url="https://example.com/rear.jpg", damages=["d_temp"]),
            ],
            aiInsights=["[Demo Simulation] Scratch on rear fender detected."],
        )
        created_insp = add_inspection(insp_in, db=self.db, current_user=self.admin_user)
        insp_id = created_insp.id
        self.assertEqual(created_insp.vehicle_id, v_temp_id)

        # 3. Check parent vehicle updated
        v_check = read_vehicle(v_temp_id, db=self.db, current_user=self.admin_user)
        self.assertEqual(v_check.health_score, 88)
        self.assertEqual(v_check.latest_inspection_date, "2025-01-10")

        # 4. Safely delete the parent vehicle
        del_resp = remove_vehicle(v_temp_id, db=self.db, current_user=self.admin_user)
        self.assertTrue(del_resp.success)
        self.assertEqual(del_resp.id, v_temp_id)

        # 5. Confirm vehicle is gone
        with self.assertRaises(HTTPException) as ctx:
            read_vehicle(v_temp_id, db=self.db, current_user=self.admin_user)
        self.assertEqual(ctx.exception.status_code, 404)

        # 6. Confirm cascade delete: linked inspection was automatically removed
        with self.assertRaises(HTTPException) as ctx:
            read_inspection(insp_id, db=self.db, current_user=self.admin_user)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_06_health_endpoint(self):
        from app.main import app, health_check
        # Verify route registration on FastAPI app
        route_paths = [getattr(route, "path", None) for route in app.routes]
        self.assertIn("/health", route_paths)
        self.assertIn("/api/health", route_paths)

        if self.db_available:
            res = health_check()
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["database"], "postgresql")
        else:
            try:
                res = health_check()
                self.assertEqual(res["status"], "ok")
                self.assertEqual(res["database"], "postgresql")
            except HTTPException as ctx:
                self.assertEqual(ctx.status_code, 503)
                self.assertEqual(ctx.detail["database"], "postgresql")
                self.assertEqual(ctx.detail["status"], "unhealthy")

    def test_07_inspection_schema_validation(self):
        from pydantic import ValidationError
        from app.schemas.inspection import CreateInspectionRequestSchema, InspectionResponse

        # 1. Create inspection request without vehicleId must fail validation
        with self.assertRaises(ValidationError):
            CreateInspectionRequestSchema(date="2026-11-05")

        # CreateInspectionRequestSchema with vehicleId alias succeeds
        req = CreateInspectionRequestSchema(vehicleId="v1", date="2026-11-05")
        self.assertEqual(req.vehicle_id, "v1")

        # CreateInspectionRequestSchema with vehicle_id snake_case succeeds
        req_snake = CreateInspectionRequestSchema(vehicle_id="v2", date="2026-11-05")
        self.assertEqual(req_snake.vehicle_id, "v2")

        # 2. Inspection response with a valid vehicleId succeeds
        resp = InspectionResponse(
            id="i_test",
            vehicleId="v1",
            date="2026-11-05",
            overallScore=85,
            totalCostMin=1000,
            totalCostMax=2000,
            aiInsights=[],
        )
        self.assertEqual(resp.vehicle_id, "v1")
        resp_dict = resp.model_dump(by_alias=True)
        self.assertEqual(resp_dict["vehicleId"], "v1")

        # 3. Legacy inspection response with vehicleId = null succeeds
        legacy_resp = InspectionResponse(
            id="i_legacy",
            vehicleId=None,
            date="2026-10-25",
            overallScore=80,
            totalCostMin=0,
            totalCostMax=0,
            aiInsights=[],
        )
        self.assertIsNone(legacy_resp.vehicle_id)
        legacy_dict = legacy_resp.model_dump(by_alias=True)
        self.assertIn("vehicleId", legacy_dict)
        self.assertIsNone(legacy_dict["vehicleId"])

    def test_08_vehicle_model_license_plate_removed(self):
        from app.models.vehicle import VehicleModel
        column_names = VehicleModel.__table__.columns.keys()
        self.assertNotIn("license_plate", column_names)
        self.assertIn("registration", column_names)

    def test_09_auth_login_schema_contract(self):
        """Verifies UserLoginRequest validation and TokenResponse contract compatibility."""
        from pydantic import ValidationError
        from app.schemas.auth import UserLoginRequest, TokenResponse, UserResponse
        from datetime import datetime

        # 1. Valid login request passes and normalizes email
        req = UserLoginRequest(email="  TestUser@Example.COM  ", password="SecretPassword123")
        self.assertEqual(req.email, "testuser@example.com")
        self.assertEqual(req.password, "SecretPassword123")

        # 2. Forbids extra fields (e.g. role or extra attacker-supplied parameters)
        with self.assertRaises(ValidationError):
            UserLoginRequest(email="valid@example.com", password="password", role="admin")

        # 3. Forbids empty password
        with self.assertRaises(ValidationError):
            UserLoginRequest(email="valid@example.com", password="")

        # 4. Forbids invalid email format
        with self.assertRaises(ValidationError):
            UserLoginRequest(email="invalid-email", password="password")

        # 5. TokenResponse serializes with accessToken and tokenType aliases matching frontend contract
        user_resp = UserResponse(id=1, email="user@example.com", role="customer", createdAt=datetime(2026, 11, 7, 12, 0))
        token_resp = TokenResponse(
            access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            token_type="bearer",
            user=user_resp,
        )
        dumped = token_resp.model_dump(by_alias=True)
        self.assertIn("accessToken", dumped)
        self.assertIn("tokenType", dumped)
        self.assertIn("user", dumped)
        self.assertEqual(dumped["accessToken"], "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")
        self.assertEqual(dumped["tokenType"], "bearer")
        self.assertEqual(dumped["user"]["email"], "user@example.com")
        self.assertEqual(dumped["user"]["role"], "customer")

    def test_10_auth_register_schema_contract(self):
        """Verifies UserRegisterRequest validation and UserResponse contract compatibility."""
        from pydantic import ValidationError
        from app.schemas.auth import UserRegisterRequest, UserResponse
        from datetime import datetime

        # 1. Valid registration passes and normalizes email
        req = UserRegisterRequest(email="  NewCustomer@Example.COM  ", password="ValidPassword123")
        self.assertEqual(req.email, "newcustomer@example.com")
        self.assertEqual(req.password, "ValidPassword123")

        # 2. Rejects password shorter than 8 characters
        with self.assertRaises(ValidationError):
            UserRegisterRequest(email="valid@example.com", password="short")

        # 3. Rejects password longer than 128 characters
        with self.assertRaises(ValidationError):
            UserRegisterRequest(email="valid@example.com", password="A" * 129)

        # 4. Forbids extra fields (Mass Assignment / Role injection prevention)
        with self.assertRaises(ValidationError):
            UserRegisterRequest(email="valid@example.com", password="ValidPassword123", role="admin")

        with self.assertRaises(ValidationError):
            UserRegisterRequest(email="valid@example.com", password="ValidPassword123", is_admin=True)

        # 5. UserResponse serializes with expected public customer fields
        resp = UserResponse(id=42, email="newcustomer@example.com", role="customer", createdAt=datetime(2026, 11, 7, 12, 0))
        dumped = resp.model_dump(by_alias=True)
        self.assertEqual(dumped["id"], 42)
        self.assertEqual(dumped["email"], "newcustomer@example.com")
        self.assertEqual(dumped["role"], "customer")
        self.assertIn("createdAt", dumped)
        self.assertNotIn("hashed_password", dumped)

if __name__ == "__main__":
    unittest.main()

