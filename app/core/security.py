"""Security utilities for authentication and authorization."""

from datetime import datetime, timedelta
from typing import Any, Optional

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import AuthenticationError

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """Create a JWT access token.

    Args:
        subject: The subject of the token (usually user_id)
        expires_delta: Optional custom expiration time
        extra_claims: Optional additional claims to include

    Returns:
        Encoded JWT token string
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.utcnow(),
    }

    if extra_claims:
        to_encode.update(extra_claims)

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token.

    Args:
        token: The JWT token string

    Returns:
        Decoded payload dict or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except ExpiredSignatureError:
        raise AuthenticationError("Token đã hết hạn, hãy login lại")
    except JWTError:
        raise AuthenticationError("Token không hợp lệ")


def get_token_subject(token: str) -> Optional[str]:
    """Extract subject (user_id) from token.

    Args:
        token: The JWT token string

    Returns:
        Subject string or None if invalid
    """
    payload = decode_token(token)
    if payload is None:
        return None
    return payload.get("sub")


# Role hierarchy for RBAC
ROLE_HIERARCHY = {
    "owner": 3,
    "admin": 2,
    "viewer": 1,
}


def check_role_permission(user_role: str, required_role: str) -> bool:
    """Check if user role has sufficient permissions.

    Args:
        user_role: The user's current role
        required_role: The minimum required role

    Returns:
        True if user has sufficient permissions
    """
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 0)
    return user_level >= required_level
