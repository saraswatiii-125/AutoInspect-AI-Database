import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.datastructures import MutableHeaders
from sqlalchemy import text
from app.config import settings
from app.database import engine, Base
from app.routers import vehicles_router, inspections_router, auth_router

# Ensure tables are created on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("TESTING"):
        try:
            Base.metadata.create_all(bind=engine)
        except Exception:
            pass
    yield

# ---------------------------------------------------------------------------
# High-Performance ASGI Middleware (No deadlocks, zero buffering)
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware:
    """Pure ASGI middleware injecting standard HTTP security headers on all responses."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["X-XSS-Protection"] = "1; mode=block"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"
            await send(message)

        await self.app(scope, receive, send_wrapper)


class RequestSizeLimitMiddleware:
    """Pure ASGI middleware enforcing maximum request body limits to prevent DOS attacks."""
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            for name, value in scope.get("headers", []):
                if name.lower() == b"content-length":
                    try:
                        if int(value) > self.max_bytes:
                            max_mb = self.max_bytes // (1024 * 1024)
                            response = JSONResponse(
                                status_code=413,
                                content={"detail": f"Payload too large. Maximum allowed size is {max_mb} MB."},
                            )
                            await response(scope, receive, send)
                            return
                    except ValueError:
                        pass
        await self.app(scope, receive, send)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    debug=False,
)

# 1. Security Headers (outermost response wrapper)
app.add_middleware(SecurityHeadersMiddleware)

# 2. Request Size Limit (rejects oversized payloads before processing)
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.MAX_REQUEST_SIZE_BYTES)

# 3. Trusted Host Middleware (prevents HTTP Host header attacks)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts,
)

# 4. Strict CORS Configuration (prohibits wildcard with credentials)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With"],
)

# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """Preserves legitimate HTTP exceptions (401, 403, 404, 429, etc.) with their headers."""
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def custom_validation_exception_handler(request: Request, exc: RequestValidationError):
    """Preserves standard 422 Unprocessable Entity validation details."""
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Masks unhandled internal server errors to prevent information disclosure."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected server error occurred. Please try again later."},
    )

# Mount API Routers
app.include_router(auth_router)
app.include_router(vehicles_router)
app.include_router(inspections_router)

@app.get("/health")
@app.get("/api/health")
def health_check():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "service": settings.PROJECT_NAME,
                "version": settings.VERSION,
                "database": "postgresql",
                "error": "Database connectivity check failed",
            },
        )
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "database": "postgresql",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
