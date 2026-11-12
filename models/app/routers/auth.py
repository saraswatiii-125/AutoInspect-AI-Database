"""
Authentication API Router for AutoInspect AI.
"""

import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.crud.user import get_user_by_email, create_user
from app.core.dependencies import get_current_user
from app.models.user import UserModel
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    TokenResponse,
)
from app.core.rate_limiter import RateLimitDependency
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Rate limiters for sensitive authentication routes
_login_rate_limiter = RateLimitDependency(
    key_prefix="login",
    max_requests=settings.RATE_LIMIT_LOGIN_PER_MIN,
    window_seconds=60,
)
_register_rate_limiter = RateLimitDependency(
    key_prefix="register",
    max_requests=settings.RATE_LIMIT_REGISTER_PER_MIN,
    window_seconds=60,
)

# Generate a genuine, valid Argon2id hash once at startup using a cryptographically random dummy secret.
# Unknown-email login attempts verify against this valid hash to prevent user enumeration timing attacks.
_DUMMY_ARGON2_HASH = hash_password(secrets.token_hex(32))


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new customer account",
    dependencies=[Depends(_register_rate_limiter)],
)
def register_user(
    register_in: UserRegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Registers a new user account.
    - Email is normalized (trimmed and lowercased).
    - Password is validated (minimum 8 characters) and hashed using Argon2id.
    - Role is strictly defaulted to 'customer' (client cannot specify a role).
    - Returns HTTP 409 if the email already exists or in case of concurrent duplicate registration.
    - Returns HTTP 201 with public UserResponse (no passwords exposed).
    """
    normalized_email = register_in.email

    # Check whether the email already exists
    existing = get_user_by_email(db, normalized_email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    # Hash the password using Argon2id
    hashed_pwd = hash_password(register_in.password)

    # Create the user with role explicitly set to 'customer'
    try:
        db_user = create_user(
            db=db,
            email=normalized_email,
            hashed_password=hashed_pwd,
            role="customer",
        )
        return db_user
    except IntegrityError:
        db.rollback()
        # Concurrency safety: catches race conditions on duplicate email insertion
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed due to an unexpected server error.",
        )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and issue JWT access token",
    dependencies=[Depends(_login_rate_limiter)],
)
def login_user(
    login_in: UserLoginRequest,
    db: Session = Depends(get_db),
):
    """
    Authenticates user credentials and issues a cryptographically signed JWT access token.
    - Normalizes email.
    - Verifies password against stored Argon2id hash.
    - Constant-time resistance to timing attacks.
    - Returns identical HTTP 401 error message for non-existent users and incorrect passwords.
    - Issues access token containing 'sub' (integer user ID as string), 'role', and 'type': 'access'.
    - Returns safe public user info (passwords strictly excluded).
    """
    normalized_email = login_in.email

    user = get_user_by_email(db, normalized_email)

    # Constant-time verification: if user not found, verify against dummy hash
    stored_hash = user.hashed_password if user else _DUMMY_ARGON2_HASH
    password_valid = verify_password(login_in.password, stored_hash)

    if not user or not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Issue JWT access token with user ID and role
    access_token = create_access_token(
        subject=user.id,
        extra_claims={"role": user.role},
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get profile of the currently authenticated user",
)
def get_current_user_profile(
    current_user: UserModel = Depends(get_current_user),
):
    """
    Retrieves the profile of the currently authenticated user.
    - Protected by get_current_user Bearer JWT dependency.
    - Identity and role are derived strictly from the database-backed UserModel.
    - Returns safe UserResponse schema (excludes hashed_password).
    """
    return current_user



