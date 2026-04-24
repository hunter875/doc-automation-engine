"""API dependencies."""

import logging
from functools import lru_cache
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AuthenticationError,
    PermissionDeniedError,
    TenantNotFoundError,
)
from app.core.security import check_role_permission, decode_token as decode_access_token
from app.infrastructure.db.session import get_db
from app.domain.models.tenant import Tenant, UserTenantRole
from app.domain.models.user import User

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials],
        Depends(security),
    ],
    db: Session = Depends(get_db),
) -> User:
    """Get current authenticated user from JWT token.

    Args:
        credentials: HTTP Bearer credentials
        db: Database session

    Returns:
        Current User model

    Raises:
        HTTPException: If authentication fails
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token không hợp lệ",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        # Convert string to UUID if needed
        from uuid import UUID
        try:
            user_uuid = UUID(str(user_id)) if isinstance(user_id, str) else user_id
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user ID in token",
            )

        user = db.query(User).filter(User.id == user_uuid).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is disabled",
            )

        return user

    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get current active user.

    Args:
        current_user: Current user from JWT

    Returns:
        Active User model

    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )
    return current_user


def get_tenant_id(
    x_tenant_id: Annotated[str, Header()],
    db: Session = Depends(get_db),
) -> str:
    """Get and validate tenant ID from header.

    Args:
        x_tenant_id: Tenant ID from X-Tenant-ID header
        db: Database session

    Returns:
        Validated tenant ID

    Raises:
        HTTPException: If tenant not found
    """
    tenant = db.query(Tenant).filter(Tenant.id == x_tenant_id).first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant not found: {x_tenant_id}",
        )

    if tenant.billing_status not in ("active",):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is disabled",
        )

    return x_tenant_id


def get_user_tenant_role(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Session = Depends(get_db),
) -> UserTenantRole:
    """Get user's role in the specified tenant.

    Args:
        current_user: Current user
        tenant_id: Tenant ID
        db: Database session

    Returns:
        UserTenantRole model

    Raises:
        HTTPException: If user has no role in tenant
    """
    user_role = (
        db.query(UserTenantRole)
        .filter(
            UserTenantRole.user_id == str(current_user.id),
            UserTenantRole.tenant_id == tenant_id,
        )
        .first()
    )

    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a member of this tenant",
        )

    return user_role


class RoleChecker:
    """Dependency class for role-based access control."""

    def __init__(self, required_role: str):
        self.required_role = required_role

    def __call__(
        self,
        user_role: Annotated[UserTenantRole, Depends(get_user_tenant_role)],
    ) -> UserTenantRole:
        """Check if user has required role or higher.

        Args:
            user_role: User's role in tenant

        Returns:
            UserTenantRole if permitted

        Raises:
            HTTPException: If permission denied
        """
        if not check_role_permission(user_role.role, self.required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires '{self.required_role}' role or higher",
            )
        return user_role


# Pre-configured role checkers
require_owner = RoleChecker("owner")
require_admin = RoleChecker("admin")
require_viewer = RoleChecker("viewer")


class TenantContext:
    """Tenant context for request."""

    def __init__(
        self,
        tenant_id: str,
        user: User,
        role: UserTenantRole,
    ):
        self.tenant_id = tenant_id
        self.user = user
        self.role = role

    @property
    def is_owner(self) -> bool:
        return self.role.role == "owner"

    @property
    def is_admin(self) -> bool:
        return self.role.role in ("owner", "admin")

    @property
    def can_upload(self) -> bool:
        return check_role_permission(self.role.role, "admin")

    @property
    def can_delete(self) -> bool:
        return check_role_permission(self.role.role, "admin")

    @property
    def can_query(self) -> bool:
        return check_role_permission(self.role.role, "viewer")


def get_tenant_context(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    user_role: Annotated[UserTenantRole, Depends(get_user_tenant_role)],
) -> TenantContext:
    """Get full tenant context for request.

    Args:
        current_user: Current user
        tenant_id: Tenant ID
        user_role: User's role in tenant

    Returns:
        TenantContext object
    """
    return TenantContext(
        tenant_id=tenant_id,
        user=current_user,
        role=user_role,
    )
