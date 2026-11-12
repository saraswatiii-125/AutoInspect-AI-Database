from app.schemas.common import DeleteResponse, ApiErrorDetail
from app.schemas.vehicle import (
    VehicleBase,
    VehicleCreate,
    VehicleUpdate,
    VehicleResponse,
)
from app.schemas.inspection import (
    BBoxSchema,
    DamageSchema,
    InspectionImageSchema,
    CreateInspectionRequestSchema,
    InspectionResponse,
)
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    TokenResponse,
    RegisterRequestSchema,
    LoginRequestSchema,
)

__all__ = [
    "DeleteResponse",
    "ApiErrorDetail",
    "VehicleBase",
    "VehicleCreate",
    "VehicleUpdate",
    "VehicleResponse",
    "BBoxSchema",
    "DamageSchema",
    "InspectionImageSchema",
    "CreateInspectionRequestSchema",
    "InspectionResponse",
    "UserRegisterRequest",
    "UserLoginRequest",
    "UserResponse",
    "TokenResponse",
    "RegisterRequestSchema",
    "LoginRequestSchema",
]

