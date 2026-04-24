"""Authentication service for user management."""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import (
    InvalidCredentialsError,
    PermissionDeniedError,
    ResourceAlreadyExistsError,
    UserNotFoundError,
)
from app.core.security import (
    check_role_permission,
    create_access_token,
    get_password_hash,
    verify_password,
)
from app.domain.models.tenant import UserTenantRole
from app.domain.models.user import User
from app.schemas.auth_schema import UserRegisterRequest

logger = logging.getLogger(__name__)


class AuthService:
    """Service for authentication operations."""

    def __init__(self, db: Session):
        self.db = db

    def register_user(self, data: UserRegisterRequest) -> User:
        """Register a new user.

        Args:
            data: Registration data with email, password, full_name

        Returns:
            Created User object

        Raises:
            ValueError: If email already exists
        """
        # Check if email already exists
        existing_user = self.db.query(User).filter(User.email == data.email).first()
        if existing_user:
            raise ResourceAlreadyExistsError(resource_type="User", detail="Email already registered")

        # Create user
        user = User(
            email=data.email,
            password_hash=get_password_hash(data.password),
            full_name=data.full_name,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        logger.info(f"User registered: {user.email}")
        return user

    def authenticate_user(self, email: str, password: str) -> User:
        """Authenticate user with email and password.

        Args:
            email: User's email
            password: Plain text password

        Returns:
            Authenticated User object

        Raises:
            InvalidCredentialsError: If credentials are invalid
        """
        user = self.db.query(User).filter(User.email == email).first()

        if not user:
            logger.warning(f"Login attempt for non-existent user: {email}")
            raise InvalidCredentialsError()

        if not verify_password(password, user.password_hash):
            logger.warning(f"Invalid password for user: {email}")
            raise InvalidCredentialsError()

        if not user.is_active:
            logger.warning(f"Login attempt for inactive user: {email}")
            raise InvalidCredentialsError("Account is deactivated")

        logger.info(f"User authenticated: {email}")
        return user

    def create_token_for_user(self, user: User) -> dict:
        """Create access token for user.

        Args:
            user: User object

        Returns:
            Dict with access_token, token_type, expires_in
        """
        from app.core.config import settings

        access_token = create_access_token(subject=str(user.id))

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    def get_user_by_id(self, user_id: UUID) -> User:
        """Get user by ID.

        Args:
            user_id: User UUID

        Returns:
            User object

        Raises:
            UserNotFoundError: If user not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise UserNotFoundError(str(user_id))
        return user

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email.

        Args:
            email: User's email

        Returns:
            User object or None
        """
        return self.db.query(User).filter(User.email == email).first()

    def get_user_tenants(self, user_id: UUID) -> list[dict]:
        """Get all tenants for a user with their roles.

        Args:
            user_id: User UUID

        Returns:
            List of tenant info dicts
        """
        roles = (
            self.db.query(UserTenantRole)
            .filter(UserTenantRole.user_id == user_id)
            .all()
        )

        tenants = []
        for role in roles:
            tenants.append(
                {
                    "tenant_id": role.tenant_id,
                    "tenant_name": role.tenant.name if role.tenant else "Unknown",
                    "role": role.role,
                }
            )

        return tenants

    def get_user_role_in_tenant(
        self,
        user_id: UUID,
        tenant_id: UUID,
    ) -> Optional[str]:
        """Get user's role in a specific tenant.

        Args:
            user_id: User UUID
            tenant_id: Tenant UUID

        Returns:
            Role string or None if not a member
        """
        role = (
            self.db.query(UserTenantRole)
            .filter(
                UserTenantRole.user_id == user_id,
                UserTenantRole.tenant_id == tenant_id,
            )
            .first()
        )

        return role.role if role else None

    def check_tenant_permission(
        self,
        user_id: UUID,
        tenant_id: UUID,
        required_role: str = "viewer",
    ) -> bool:
        """Check if user has required permission in tenant.

        Args:
            user_id: User UUID
            tenant_id: Tenant UUID
            required_role: Minimum required role

        Returns:
            True if user has permission

        Raises:
            PermissionDeniedError: If user lacks permission
        """
        user_role = self.get_user_role_in_tenant(user_id, tenant_id)

        if not user_role:
            raise PermissionDeniedError(
                message="You are not a member of this tenant",
                required_role=required_role,
            )

        if not check_role_permission(user_role, required_role):
            raise PermissionDeniedError(
                message=f"This action requires '{required_role}' role or higher",
                required_role=required_role,
            )

        return True

    def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
    ) -> bool:
        """Change user's password.

        Args:
            user: User object
            current_password: Current password
            new_password: New password

        Returns:
            True if successful

        Raises:
            InvalidCredentialsError: If current password is wrong
        """
        if not verify_password(current_password, user.password_hash):
            raise InvalidCredentialsError("Current password is incorrect")

        user.password_hash = get_password_hash(new_password)
        self.db.commit()

        logger.info(f"Password changed for user: {user.email}")
        return True

    def deactivate_user(self, user: User) -> bool:
        """Deactivate a user account.

        Args:
            user: User object

        Returns:
            True if successful
        """
        user.is_active = False
        self.db.commit()

        logger.info(f"User deactivated: {user.email}")
        return True
