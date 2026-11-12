from app.routers.vehicles import router as vehicles_router
from app.routers.inspections import router as inspections_router
from app.routers.auth import router as auth_router

__all__ = ["vehicles_router", "inspections_router", "auth_router"]

