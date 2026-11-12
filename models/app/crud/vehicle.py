import time
from typing import List, Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.models.vehicle import VehicleModel
from app.schemas.vehicle import VehicleCreate, VehicleUpdate, VehicleResponse
from app.schemas.common import DeleteResponse

def to_vehicle_response(v: VehicleModel) -> VehicleResponse:
    """Helper to convert VehicleModel to VehicleResponse with inspection IDs."""
    return VehicleResponse(
        id=v.id,
        make=v.make,
        model=v.model,
        year=v.year,
        registration=v.registration,
        color=v.color,
        image=v.image,
        inspections=[insp.id for insp in v.inspections] if v.inspections else [],
        healthScore=v.health_score,
        latestInspectionDate=v.latest_inspection_date,
    )

def get_vehicles(
    db: Session,
    user_id: Optional[int] = None,
    include_unassigned: bool = False,
) -> List[VehicleModel]:
    query = db.query(VehicleModel)
    if user_id is not None:
        if include_unassigned:
            query = query.filter(
                or_(
                    VehicleModel.user_id == user_id,
                    VehicleModel.user_id.is_(None),
                )
            )
        else:
            query = query.filter(VehicleModel.user_id == user_id)
    return query.order_by(VehicleModel.created_at.desc()).all()

def get_vehicle(
    db: Session,
    vehicle_id: str,
    user_id: Optional[int] = None,
) -> Optional[VehicleModel]:
    query = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id)
    if user_id is not None:
        query = query.filter(VehicleModel.user_id == user_id)
    return query.first()

def get_vehicle_by_registration(db: Session, registration: str) -> Optional[VehicleModel]:
    return db.query(VehicleModel).filter(VehicleModel.registration == registration).first()

def create_vehicle(
    db: Session,
    vehicle_in: VehicleCreate,
    custom_id: Optional[str] = None,
    user_id: Optional[int] = None,
) -> VehicleModel:
    new_id = custom_id or f"v_{int(time.time() * 1000)}"
    db_vehicle = VehicleModel(
        id=new_id,
        user_id=user_id,
        make=vehicle_in.make,
        model=vehicle_in.model,
        year=vehicle_in.year,
        registration=vehicle_in.registration,
        color=vehicle_in.color,
        image=vehicle_in.image,
        health_score=100,
        latest_inspection_date=None,
    )
    try:
        db.add(db_vehicle)
        db.commit()
        db.refresh(db_vehicle)
        return db_vehicle
    except Exception:
        db.rollback()
        raise

ALLOWED_VEHICLE_UPDATE_FIELDS = {
    "make",
    "model",
    "year",
    "registration",
    "color",
    "image",
    "health_score",
    "latest_inspection_date",
}

def update_vehicle(
    db: Session,
    db_vehicle: VehicleModel,
    vehicle_in: VehicleUpdate,
) -> VehicleModel:
    update_data = vehicle_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in ALLOWED_VEHICLE_UPDATE_FIELDS and hasattr(db_vehicle, field):
            setattr(db_vehicle, field, value)

    try:
        db.add(db_vehicle)
        db.commit()
        db.refresh(db_vehicle)
        return db_vehicle
    except Exception:
        db.rollback()
        raise

def delete_vehicle(db: Session, db_vehicle: VehicleModel) -> DeleteResponse:
    """
    Safely deletes a vehicle.
    Foreign-key cascade deletes all linked inspections in the same transaction.
    """
    vehicle_id = db_vehicle.id
    try:
        db.delete(db_vehicle)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return DeleteResponse(
        success=True,
        id=vehicle_id,
        message="Vehicle and linked inspections deleted successfully",
    )
