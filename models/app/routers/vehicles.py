from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import UserModel
from app.schemas.vehicle import VehicleCreate, VehicleUpdate, VehicleResponse
from app.schemas.common import DeleteResponse
from app.crud.vehicle import (
    get_vehicles,
    get_vehicle,
    get_vehicle_by_registration,
    create_vehicle,
    update_vehicle,
    delete_vehicle,
    to_vehicle_response,
)

router = APIRouter(prefix="/api/vehicles", tags=["Vehicles"])

def _check_role(user: UserModel) -> None:
    if user.role not in ("admin", "customer"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Invalid or unauthorized role.",
        )

@router.get("", response_model=List[VehicleResponse])
def list_vehicles(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Fetch vehicles filtered by authenticated user role and ownership."""
    _check_role(current_user)

    if current_user.role == "admin":
        vehicles = get_vehicles(db)
    else:
        vehicles = get_vehicles(db, user_id=current_user.id, include_unassigned=False)

    return [to_vehicle_response(v) for v in vehicles]

@router.get("/{vehicle_id}", response_model=VehicleResponse)
def read_vehicle(
    vehicle_id: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Fetch a single vehicle by ID with ownership enforcement."""
    _check_role(current_user)

    if current_user.role == "admin":
        db_vehicle = get_vehicle(db, vehicle_id)
    else:
        db_vehicle = get_vehicle(db, vehicle_id, user_id=current_user.id)

    if not db_vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle with ID '{vehicle_id}' not found",
        )
    return to_vehicle_response(db_vehicle)

@router.post("", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
def add_vehicle(
    vehicle_in: VehicleCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Create a new vehicle assigned to the authenticated user."""
    _check_role(current_user)

    existing = get_vehicle_by_registration(db, vehicle_in.registration)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Vehicle with registration '{vehicle_in.registration}' already exists",
        )
    db_vehicle = create_vehicle(
        db,
        vehicle_in,
        custom_id=vehicle_in.id,
        user_id=current_user.id,
    )
    return to_vehicle_response(db_vehicle)

@router.put("/{vehicle_id}", response_model=VehicleResponse)
def edit_vehicle(
    vehicle_id: str,
    vehicle_in: VehicleUpdate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Update an existing vehicle with ownership enforcement."""
    _check_role(current_user)

    if current_user.role == "admin":
        db_vehicle = get_vehicle(db, vehicle_id)
    else:
        db_vehicle = get_vehicle(db, vehicle_id, user_id=current_user.id)

    if not db_vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle with ID '{vehicle_id}' not found",
        )

    # Check whether the requested registration number belongs to a different vehicle
    if vehicle_in.registration is not None and vehicle_in.registration.strip() != "":
        conflict = get_vehicle_by_registration(db, vehicle_in.registration.strip())
        if conflict and conflict.id != vehicle_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Registration number already exists.",
            )

    try:
        updated = update_vehicle(db, db_vehicle, vehicle_in)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration number already exists.",
        )
    return to_vehicle_response(updated)

@router.delete("/{vehicle_id}", response_model=DeleteResponse)
def remove_vehicle(
    vehicle_id: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Safely delete a vehicle with ownership enforcement."""
    _check_role(current_user)

    if current_user.role == "admin":
        db_vehicle = get_vehicle(db, vehicle_id)
    else:
        db_vehicle = get_vehicle(db, vehicle_id, user_id=current_user.id)

    if not db_vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle with ID '{vehicle_id}' not found",
        )
    return delete_vehicle(db, db_vehicle)
