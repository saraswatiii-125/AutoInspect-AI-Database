import time
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.inspection import InspectionModel
from app.models.vehicle import VehicleModel
from app.schemas.inspection import (
    CreateInspectionRequestSchema,
    InspectionResponse,
    DamageSchema,
    InspectionImageSchema,
)

def to_inspection_response(insp: InspectionModel) -> InspectionResponse:
    """Helper to convert InspectionModel to InspectionResponse with exact camelCase JSON keys."""
    damages_list = [
        DamageSchema.model_validate(d) if isinstance(d, dict) else d
        for d in (insp.damages or [])
    ]
    images_list = [
        InspectionImageSchema.model_validate(img) if isinstance(img, dict) else img
        for img in (insp.images or [])
    ]

    return InspectionResponse(
        id=insp.id,
        vehicleId=insp.vehicle_id,
        date=insp.date,
        status=insp.status,
        damages=damages_list,
        images=images_list,
        overallScore=insp.overall_score,
        totalCostMin=insp.total_cost_min,
        totalCostMax=insp.total_cost_max,
        aiInsights=insp.ai_insights or [],
    )

def get_inspections(
    db: Session,
    vehicle_id: Optional[str] = None,
    user_id: Optional[int] = None,
) -> List[InspectionModel]:
    query = db.query(InspectionModel)
    if user_id is not None:
        query = query.join(
            VehicleModel,
            InspectionModel.vehicle_id == VehicleModel.id,
        ).filter(VehicleModel.user_id == user_id)
    if vehicle_id and isinstance(vehicle_id, str):
        query = query.filter(InspectionModel.vehicle_id == vehicle_id)
    return query.order_by(InspectionModel.date.desc(), InspectionModel.created_at.desc()).all()

def get_inspection(
    db: Session,
    inspection_id: str,
    user_id: Optional[int] = None,
) -> Optional[InspectionModel]:
    query = db.query(InspectionModel).filter(InspectionModel.id == inspection_id)
    if user_id is not None:
        query = query.join(
            VehicleModel,
            InspectionModel.vehicle_id == VehicleModel.id,
        ).filter(VehicleModel.user_id == user_id)
    return query.first()

def create_inspection(
    db: Session,
    inspection_in: CreateInspectionRequestSchema,
    custom_id: Optional[str] = None,
    user_id: Optional[int] = None,
) -> InspectionModel:
    new_id = custom_id or f"i_{int(time.time() * 1000)}"
    date_str = inspection_in.date or datetime.utcnow().strftime("%Y-%m-%d")

    damages_data = [d.model_dump(by_alias=True) for d in (inspection_in.damages or [])]
    images_data = [img.model_dump(by_alias=True) for img in (inspection_in.images or [])]

    # Calculate total costs if not explicitly provided
    total_min = inspection_in.total_cost_min
    total_max = inspection_in.total_cost_max
    if (total_min == 0 or total_min is None) and damages_data:
        total_min = sum(d.get("costMin", 0) for d in damages_data)
    if (total_max == 0 or total_max is None) and damages_data:
        total_max = sum(d.get("costMax", 0) for d in damages_data)

    db_inspection = InspectionModel(
        id=new_id,
        vehicle_id=inspection_in.vehicle_id,
        user_id=user_id,
        date=date_str,
        status=inspection_in.status or "completed",
        overall_score=inspection_in.overall_score or 80,
        total_cost_min=total_min or 0,
        total_cost_max=total_max or 0,
        damages=damages_data,
        images=images_data,
        ai_insights=inspection_in.ai_insights or [],
    )
    try:
        db.add(db_inspection)

        # Update parent vehicle's health score and latest inspection date
        parent_vehicle = db.query(VehicleModel).filter(VehicleModel.id == inspection_in.vehicle_id).first()
        if parent_vehicle:
            parent_vehicle.health_score = db_inspection.overall_score
            parent_vehicle.latest_inspection_date = db_inspection.date
            db.add(parent_vehicle)

        db.commit()
        db.refresh(db_inspection)
        return db_inspection
    except Exception:
        db.rollback()
        raise
