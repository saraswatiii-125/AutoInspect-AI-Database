"""
Authentication Pydantic schemas for AutoInspect AI.
Handles registration, login, user serialization, and token responses.
"""

from datetime import datetime
import re
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator

# RFC 5322 compliant regex for email validation (forbids consecutive dots, leading dots, and invalid domains)
EMAIL_REGEX = re.compile(
    r"^(?!\.)(?!.*\.\.)([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)$"
)


def normalize_and_validate_email(v: str) -> str:
    """Helper to validate and normalize email addresses (trimmed and lowercased)."""
    if not isinstance(v, str):
        raise ValueError("Email must be a string.")
    normalized = v.strip().lower()
    if not normalized:
        raise ValueError("Email address cannot be empty.")
    if len(normalized) > 255:
        raise ValueError("Email address cannot exceed 255 characters.")
    if not EMAIL_REGEX.match(normalized):
        raise ValueError("Invalid email address format.")
    return normalized


# ==========================================
# Request Schemas
# ==========================================

class UserRegisterRequest(BaseModel):
    """
    Schema for user registration.
    Enforces minimum 8 characters password and valid email.
    Explicitly forbids client-provided 'role' or unexpected extra fields (Mass Assignment Prevention).
    """
    email: str
    password: str = Field(min_length=8, max_length=128, description="Password must be at least 8 characters long.")

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=False,
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return normalize_and_validate_email(v)


class UserLoginRequest(BaseModel):
    """
    Schema for JSON user login.
    """
    email: str
    password: str = Field(min_length=1, max_length=128, description="Password cannot be empty and must not exceed 128 characters.")

    model_config = ConfigDict(
        extra="forbid",
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return normalize_and_validate_email(v)


# ==========================================
# Response Schemas
# ==========================================

class UserResponse(BaseModel):
    """
    Safe public user representation.
    Strictly excludes hashed_password and sensitive attributes.
    Supports both snake_case and camelCase serialization.
    """
    id: int
    email: str
    role: str
    created_at: Optional[datetime] = Field(default=None, alias="createdAt")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class TokenResponse(BaseModel):
    """
    Schema for JWT token response returned upon successful authentication.
    """
    access_token: str = Field(alias="accessToken")
    token_type: str = Field(default="bearer", alias="tokenType")
    user: UserResponse

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


# Aliases for naming flexibility
RegisterRequestSchema = UserRegisterRequest
LoginRequestSchema = UserLoginRequest
