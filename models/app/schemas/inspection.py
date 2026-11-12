from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Literal

class BBoxSchema(BaseModel):
    x: float
    y: float
    w: float
    h: float

class DamageSchema(BaseModel):
    id: str
    part: str
    type: str
    severity: Literal["minor", "moderate", "severe"]
    confidence: float
    cost_min: int = Field(alias="costMin")
    cost_max: int = Field(alias="costMax")
    recommendation: str
    bbox: BBoxSchema
    image_index: int = Field(alias="imageIndex")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        serialize_by_alias=True,
    )

class InspectionImageSchema(BaseModel):
    label: str
    url: str
    damages: List[str] = []

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        serialize_by_alias=True,
    )

class CreateInspectionRequestSchema(BaseModel):
    """Directly matches TypeScript CreateInspectionRequest contract."""
    id: Optional[str] = None
    vehicle_id: str = Field(alias="vehicleId")
    date: Optional[str] = None
    status: Optional[Literal["completed", "processing", "pending"]] = "completed"
    damages: Optional[List[DamageSchema]] = []
    images: Optional[List[InspectionImageSchema]] = []
    overall_score: Optional[int] = Field(80, ge=0, le=100, alias="overallScore")
    total_cost_min: Optional[int] = Field(0, ge=0, alias="totalCostMin")
    total_cost_max: Optional[int] = Field(0, ge=0, alias="totalCostMax")
    ai_insights: Optional[List[str]] = Field(default=[], alias="aiInsights")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        serialize_by_alias=True,
        extra="forbid",
    )

class InspectionResponse(BaseModel):
    """Directly matches TypeScript Inspection contract with exact camelCase JSON keys."""
    id: str
    vehicle_id: Optional[str] = Field(default=None, alias="vehicleId")
    date: str
    status: Literal["completed", "processing", "pending"] = "completed"
    damages: List[DamageSchema] = []
    images: List[InspectionImageSchema] = []
    overall_score: int = Field(alias="overallScore")
    total_cost_min: int = Field(alias="totalCostMin")
    total_cost_max: int = Field(alias="totalCostMax")
    ai_insights: List[str] = Field(alias="aiInsights")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        serialize_by_alias=True,
    )


