"""
Authentication and authorization dependencies for AutoInspect AI.
Provides get_current_user for protecting endpoints with JWT Bearer authentication.
"""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.security import decode_access_token
from app.crud.user import get_user_by_id
from app.models.user import UserModel

# HTTPBearer security scheme extracting tokens exclusively from the Authorization header.
# auto_error=False allows uniform RFC 6750 HTTP 401 Unauthorized responses with WWW-Authenticate headers.
_http_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    auth_credentials: Optional[HTTPAuthorizationCredentials] = Depends(_http_bearer),
    db: Session = Depends(get_db),
) -> UserModel:
    """
    Reusable FastAPI dependency that verifies the Bearer JWT token from the
    Authorization header, validates cryptographic claims, and returns the authenticated
    UserModel directly from the database.

    - Extracts token exclusively from the Authorization header.
    - Rejects missing, malformed, expired, or invalid tokens with HTTP 401.
    - Requires JWT type claim to equal 'access'.
    - Validates subject claim and safely converts it to an integer user ID.
    - Loads the user from public.users using get_user_by_id().
    - Rejects tokens referencing deleted or non-existent users with HTTP 401.
    - Obtains role strictly from database state (never trusts client-supplied roles).
    - Returns HTTP 401 with 'WWW-Authenticate: Bearer' on any authentication failure.
    """
    auth_failure_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Verify Authorization header presence and Bearer scheme
    if (
        auth_credentials is None
        or not auth_credentials.credentials
        or auth_credentials.scheme.lower() != "bearer"
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_credentials.credentials

    # 2. Verify cryptographic signature, expiration, and format
    try:
        payload = decode_access_token(token)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (InvalidTokenError, Exception):
        raise auth_failure_exception

    # 3. Require token type claim to equal 'access'
    if payload.get("type") != "access":
        raise auth_failure_exception

    # 4. Extract subject claim and safely convert to integer user ID
    sub = payload.get("sub")
    if not sub:
        raise auth_failure_exception

    try:
        user_id = int(sub)
    except (ValueError, TypeError):
        raise auth_failure_exception

    # 5. Load current user from database (verifies existence & fetches true role)
    user = get_user_by_id(db, user_id=user_id)
    if user is None:
        raise auth_failure_exception

    return user

