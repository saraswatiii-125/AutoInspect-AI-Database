from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import UserModel
from app.schemas.inspection import (
    CreateInspectionRequestSchema,
    InspectionResponse,
)
from app.crud.inspection import (
    get_inspections,
    get_inspection,
    create_inspection,
    to_inspection_response,
)
from app.crud.vehicle import get_vehicle

router = APIRouter(prefix="/api/inspections", tags=["Inspections"])

def _check_role(user: UserModel) -> None:
    if user.role not in ("admin", "customer"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Invalid or unauthorized role.",
        )

@router.get("", response_model=List[InspectionResponse])
def list_inspections(
    vehicle_id: Optional[str] = Query(None, alias="vehicleId"),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Fetch inspection history with authentication and ownership enforcement."""
    _check_role(current_user)
    filter_id = vehicle_id if isinstance(vehicle_id, str) else None

    if current_user.role == "admin":
        inspections = get_inspections(db, vehicle_id=filter_id)
    else:
        inspections = get_inspections(db, vehicle_id=filter_id, user_id=current_user.id)

    return [to_inspection_response(i) for i in inspections]

@router.get("/{inspection_id}", response_model=InspectionResponse)
def read_inspection(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Fetch a single inspection by ID with authentication and ownership enforcement."""
    _check_role(current_user)

    if current_user.role == "admin":
        db_inspection = get_inspection(db, inspection_id)
    else:
        db_inspection = get_inspection(db, inspection_id, user_id=current_user.id)

    if not db_inspection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inspection with ID '{inspection_id}' not found",
        )
    return to_inspection_response(db_inspection)

@router.post("", response_model=InspectionResponse, status_code=status.HTTP_201_CREATED)
def add_inspection(
    inspection_in: CreateInspectionRequestSchema,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Create a new inspection report linked to a vehicle with ownership verification."""
    _check_role(current_user)

    if current_user.role == "admin":
        parent_vehicle = get_vehicle(db, inspection_in.vehicle_id)
    else:
        parent_vehicle = get_vehicle(db, inspection_in.vehicle_id, user_id=current_user.id)

    if not parent_vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target vehicle with ID '{inspection_in.vehicle_id}' not found",
        )

    db_inspection = create_inspection(
        db,
        inspection_in,
        custom_id=inspection_in.id,
        user_id=current_user.id,
    )
    return to_inspection_response(db_inspection)
