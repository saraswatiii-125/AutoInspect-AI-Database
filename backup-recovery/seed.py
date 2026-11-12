"""Seed script populating initial PostgreSQL database with vehicles and inspections from src/data.ts."""

import sys as _sys
from pathlib import Path as _Path
_MODELS_DIR = _Path(__file__).resolve().parent.parent / 'models'
if str(_MODELS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_MODELS_DIR))
import sys
from pathlib import Path

# Add backend directory and vendor directory to path
backend_dir = Path(__file__).resolve().parent
vendor_dir = backend_dir / "vendor"
if vendor_dir.exists() and str(vendor_dir) not in sys.path:
    sys.path.insert(0, str(vendor_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
project_dir = backend_dir.parent
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))

from app.database import engine, Base, SessionLocal
from app.models.vehicle import VehicleModel
from app.models.inspection import InspectionModel

def seed_database():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Check if vehicles already seeded
        existing = db.query(VehicleModel).first()
        if existing:
            print("Database already contains seed data. Skipping seed.")
            return

        print("Seeding initial vehicles and inspections matching src/data.ts...")

        # 1. Vehicles
        v1 = VehicleModel(
            id="v1",
            make="BMW",
            model="5 Series",
            year=2019,
            registration="MH-12-AB-2026",
            color="Alpine White",
            image="https://images.unsplash.com/photo-1555215695-3004980ad54e?w=600&h=380&fit=crop&auto=format",
            health_score=78,
            latest_inspection_date="2024-12-18",
        )
        v2 = VehicleModel(
            id="v2",
            make="Toyota",
            model="Fortuner",
            year=2021,
            registration="KA-05-MN-4321",
            color="Phantom Brown",
            image="https://images.unsplash.com/photo-1544636331-e26879cd4d9b?w=600&h=380&fit=crop&auto=format",
            health_score=92,
            latest_inspection_date="2024-11-30",
        )
        v3 = VehicleModel(
            id="v3",
            make="Hyundai",
            model="Creta",
            year=2022,
            registration="DL-01-CZ-8890",
            color="Typhoon Silver",
            image="https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=600&h=380&fit=crop&auto=format",
            health_score=97,
            latest_inspection_date=None,
        )

        db.add_all([v1, v2, v3])
        db.commit()

        # 2. Inspections
        i1 = InspectionModel(
            id="i1",
            vehicle_id="v1",
            date="2024-12-18",
            status="completed",
            overall_score=78,
            total_cost_min=17000,
            total_cost_max=26000,
            damages=[
                {
                    "id": "d1",
                    "part": "Front Bumper",
                    "type": "Dent",
                    "severity": "moderate",
                    "confidence": 94,
                    "costMin": 5000,
                    "costMax": 8000,
                    "recommendation": "Repair Recommended",
                    "bbox": {"x": 5, "y": 52, "w": 22, "h": 30},
                    "imageIndex": 0,
                },
                {
                    "id": "d2",
                    "part": "Left Door",
                    "type": "Scratch",
                    "severity": "minor",
                    "confidence": 91,
                    "costMin": 2000,
                    "costMax": 4000,
                    "recommendation": "Repainting Recommended",
                    "bbox": {"x": 38, "y": 40, "w": 18, "h": 35},
                    "imageIndex": 2,
                },
                {
                    "id": "d3",
                    "part": "Left Headlight",
                    "type": "Broken",
                    "severity": "severe",
                    "confidence": 96,
                    "costMin": 6000,
                    "costMax": 9000,
                    "recommendation": "Replacement Recommended",
                    "bbox": {"x": 6, "y": 38, "w": 14, "h": 22},
                    "imageIndex": 0,
                },
                {
                    "id": "d4",
                    "part": "Bonnet",
                    "type": "Dent",
                    "severity": "moderate",
                    "confidence": 88,
                    "costMin": 4000,
                    "costMax": 5000,
                    "recommendation": "Professional Inspection Recommended",
                    "bbox": {"x": 28, "y": 30, "w": 30, "h": 25},
                    "imageIndex": 0,
                },
            ],
            images=[
                {
                    "label": "Front",
                    "url": "https://images.unsplash.com/photo-1555215695-3004980ad54e?w=800&h=550&fit=crop&auto=format",
                    "damages": ["d1", "d3", "d4"],
                },
                {
                    "label": "Rear",
                    "url": "https://images.unsplash.com/photo-1494976388531-d1058494cdd8?w=800&h=550&fit=crop&auto=format",
                    "damages": [],
                },
                {
                    "label": "Left Side",
                    "url": "https://images.unsplash.com/photo-1788639477143-61eaa06c630f?w=800&h=550&fit=crop&auto=format",
                    "damages": ["d2"],
                },
                {
                    "label": "Right Side",
                    "url": "https://images.unsplash.com/photo-1760713164476-7eb5063b3d07?w=800&h=550&fit=crop&auto=format",
                    "damages": [],
                },
                {
                    "label": "Close-up",
                    "url": "https://images.unsplash.com/photo-1703609438732-2fad53e62a4b?w=800&h=550&fit=crop&auto=format",
                    "damages": ["d2"],
                },
            ],
            ai_insights=[
                "[Demo Simulation] Front bumper dent is moderate — panel repair likely sufficient; no structural damage detected.",
                "[Demo Simulation] Left door scratch is surface-level and may only require professional repainting.",
                "[Demo Simulation] Left headlight is critically damaged — replacement strongly recommended before driving.",
                "[Demo Simulation] Bonnet dent detected near center — recommend PDR (Paintless Dent Repair) evaluation.",
            ],
        )

        i2 = InspectionModel(
            id="i2",
            vehicle_id="v1",
            date="2024-08-05",
            status="completed",
            overall_score=85,
            total_cost_min=8000,
            total_cost_max=12000,
            damages=[
                {
                    "id": "d5",
                    "part": "Rear Bumper",
                    "type": "Scratch",
                    "severity": "minor",
                    "confidence": 89,
                    "costMin": 3000,
                    "costMax": 5000,
                    "recommendation": "Repainting Recommended",
                    "bbox": {"x": 20, "y": 55, "w": 60, "h": 28},
                    "imageIndex": 1,
                },
                {
                    "id": "d6",
                    "part": "Right Fender",
                    "type": "Dent",
                    "severity": "moderate",
                    "confidence": 86,
                    "costMin": 5000,
                    "costMax": 7000,
                    "recommendation": "Repair Recommended",
                    "bbox": {"x": 60, "y": 35, "w": 22, "h": 30},
                    "imageIndex": 3,
                },
            ],
            images=[
                {
                    "label": "Front",
                    "url": "https://images.unsplash.com/photo-1555215695-3004980ad54e?w=800&h=550&fit=crop&auto=format",
                    "damages": [],
                },
                {
                    "label": "Rear",
                    "url": "https://images.unsplash.com/photo-1494976388531-d1058494cdd8?w=800&h=550&fit=crop&auto=format",
                    "damages": ["d5"],
                },
                {
                    "label": "Left Side",
                    "url": "https://images.unsplash.com/photo-1760713164476-7eb5063b3d07?w=800&h=550&fit=crop&auto=format",
                    "damages": [],
                },
                {
                    "label": "Right Side",
                    "url": "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=800&h=550&fit=crop&auto=format",
                    "damages": ["d6"],
                },
                {
                    "label": "Close-up",
                    "url": "https://images.unsplash.com/photo-1788639477143-61eaa06c630f?w=800&h=550&fit=crop&auto=format",
                    "damages": ["d5"],
                },
            ],
            ai_insights=[
                "[Demo Simulation] Rear bumper scratch appears surface-level — repainting should restore appearance.",
                "[Demo Simulation] Right fender dent is moderate — PDR recommended.",
            ],
        )

        i3 = InspectionModel(
            id="i3",
            vehicle_id="v2",
            date="2024-11-30",
            status="completed",
            overall_score=92,
            total_cost_min=4000,
            total_cost_max=6500,
            damages=[
                {
                    "id": "d7",
                    "part": "Front Grille",
                    "type": "Crack",
                    "severity": "minor",
                    "confidence": 92,
                    "costMin": 4000,
                    "costMax": 6500,
                    "recommendation": "Replacement Recommended",
                    "bbox": {"x": 30, "y": 42, "w": 40, "h": 25},
                    "imageIndex": 0,
                },
            ],
            images=[
                {
                    "label": "Front",
                    "url": "https://images.unsplash.com/photo-1544636331-e26879cd4d9b?w=800&h=550&fit=crop&auto=format",
                    "damages": ["d7"],
                },
                {
                    "label": "Rear",
                    "url": "https://images.unsplash.com/photo-1494976388531-d1058494cdd8?w=800&h=550&fit=crop&auto=format",
                    "damages": [],
                },
                {
                    "label": "Left Side",
                    "url": "https://images.unsplash.com/photo-1760713164476-7eb5063b3d07?w=800&h=550&fit=crop&auto=format",
                    "damages": [],
                },
                {
                    "label": "Right Side",
                    "url": "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=800&h=550&fit=crop&auto=format",
                    "damages": [],
                },
                {
                    "label": "Close-up",
                    "url": "https://images.unsplash.com/photo-1703609438732-2fad53e62a4b?w=800&h=550&fit=crop&auto=format",
                    "damages": [],
                },
            ],
            ai_insights=[
                "[Demo Simulation] Front grille crack is minor — replacement recommended for optimal aesthetic.",
            ],
        )

        db.add_all([i1, i2, i3])
        db.commit()
        print("Successfully seeded database with 3 vehicles and 3 inspections.")

    finally:
        db.close()

if __name__ == "__main__":
    seed_database()

