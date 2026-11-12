from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List

class VehicleBase(BaseModel):
    make: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=1900, le=2100)
    registration: str = Field(min_length=1, max_length=50)
    color: str = Field(min_length=1, max_length=50)
    image: str = Field(max_length=5000000)

    model_config = ConfigDict(extra="forbid")

class VehicleCreate(VehicleBase):
    """Directly matches TypeScript CreateVehicleRequest contract."""
    id: Optional[str] = None

class VehicleUpdate(BaseModel):
    """Directly matches TypeScript UpdateVehicleRequest contract."""
    make: Optional[str] = Field(None, min_length=1, max_length=100)
    model: Optional[str] = Field(None, min_length=1, max_length=100)
    year: Optional[int] = Field(None, ge=1900, le=2100)
    registration: Optional[str] = Field(None, min_length=1, max_length=50)
    color: Optional[str] = Field(None, min_length=1, max_length=50)
    image: Optional[str] = Field(None, max_length=5000000)
    health_score: Optional[int] = Field(None, ge=0, le=100, alias="healthScore")
    latest_inspection_date: Optional[str] = Field(None, max_length=50, alias="latestInspectionDate")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

class VehicleResponse(VehicleBase):
    """Directly matches TypeScript Vehicle contract with exact camelCase JSON keys."""
    id: str
    year: int = Field(ge=0, le=2100)  # Allows historical legacy record year=0
    inspections: List[str] = []
    health_score: int = Field(100, alias="healthScore")
    latest_inspection_date: Optional[str] = Field(None, alias="latestInspectionDate")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        serialize_by_alias=True,
    )

