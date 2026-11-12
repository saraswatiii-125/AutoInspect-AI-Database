"""
Security and authentication utilities for AutoInspect AI.
Provides Argon2id password hashing and PyJWT access token creation/verification.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union
from argon2 import PasswordHasher
from argon2.exceptions import (
    VerifyMismatchError,
    InvalidHashError,
    VerificationError,
)
import jwt
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidSignatureError,
    DecodeError,
    InvalidTokenError,
)

from app.config import settings

# ---------------------------------------------------------------------------
# Argon2id Password Security
# ---------------------------------------------------------------------------
# PasswordHasher defaults to Argon2id (Type 2), recommended by OWASP.
# Parameters: 64 MiB RAM, 3 iterations, 4 parallelism lanes, 32-byte hash.
_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """
    Hashes a plain-text password using Argon2id with cryptographically secure random salt.

    Args:
        password: The plain-text password to hash.

    Returns:
        Argon2id encoded hash string containing algorithm parameters, salt, and hash.

    Raises:
        ValueError: If password is empty or not a string.
    """
    if not password or not isinstance(password, str):
        raise ValueError("Password must be a non-empty string.")
    return _password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain-text password against an Argon2 hash in constant time.
    Safely handles invalid hashes, corrupted formatting, or mismatched passwords
    without raising unhandled exceptions.

    Args:
        plain_password: The plain-text password to test.
        hashed_password: The stored Argon2 hash to verify against.

    Returns:
        True if the password matches, False otherwise.
    """
    if not plain_password or not hashed_password:
        return False
    if not isinstance(plain_password, str) or not isinstance(hashed_password, str):
        return False

    try:
        return _password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False
    except Exception:
        # Fallback safeguard against any unexpected parsing errors
        return False


def needs_rehash(hashed_password: str) -> bool:
    """
    Checks if a stored Argon2 hash was created with older/weaker parameters.

    Args:
        hashed_password: Stored Argon2 hash.

    Returns:
        True if the hash should be re-generated, False otherwise.
    """
    if not hashed_password or not isinstance(hashed_password, str):
        return False
    try:
        return _password_hasher.check_needs_rehash(hashed_password)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# PyJWT Access Token Security
# ---------------------------------------------------------------------------
TOKEN_TYPE_ACCESS = "access"


def create_access_token(
    subject: Union[str, int],
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Creates a cryptographically signed JWT access token using HS256.

    Args:
        subject: The user's database ID (integer or string) assigned to the 'sub' claim.
        expires_delta: Optional custom token expiration duration. If omitted,
                       uses settings.ACCESS_TOKEN_EXPIRE_MINUTES.
        extra_claims: Optional additional claims to include in the payload (e.g. role, email).

    Returns:
        Encoded JWT token string.

    Raises:
        ValueError: If subject is empty or missing.
    """
    if subject is None or str(subject).strip() == "":
        raise ValueError("Token subject ('sub') cannot be empty.")

    now = datetime.now(timezone.utc)
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": str(subject),
        "type": TOKEN_TYPE_ACCESS,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    if extra_claims:
        # Prevent overriding reserved claims
        for k, v in extra_claims.items():
            if k not in ("sub", "type", "exp", "iat"):
                payload[k] = v

    secret = settings.JWT_SECRET_KEY
    algorithm = settings.JWT_ALGORITHM

    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Verifies and decodes a JWT access token.
    Enforces signature validity, expiration, algorithm, presence of 'sub',
    and token type ('access').

    Args:
        token: Encoded JWT string.

    Returns:
        Decoded payload dictionary.

    Raises:
        ExpiredSignatureError: If the token has expired.
        InvalidTokenError: If the token is malformed, has an invalid signature,
                           missing 'sub', or wrong token type.
    """
    if not token or not isinstance(token, str):
        raise InvalidTokenError("Token string must be non-empty.")

    secret = settings.JWT_SECRET_KEY
    algorithm = settings.JWT_ALGORITHM

    # Decode and verify signature, expiration, and required standard claims
    payload = jwt.decode(
        token,
        secret,
        algorithms=[algorithm],
        options={"require": ["exp", "iat", "sub"]},
    )

    # Validate token type claim
    token_type = payload.get("type")
    if token_type != TOKEN_TYPE_ACCESS:
        raise InvalidTokenError(
            f"Invalid token type: expected '{TOKEN_TYPE_ACCESS}', got '{token_type}'."
        )

    # Validate subject claim
    sub = payload.get("sub")
    if not sub or not str(sub).strip():
        raise InvalidTokenError("Token 'sub' claim is empty or missing.")

    return payload

