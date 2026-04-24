"""Tenant management API endpoints."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    TenantContext,
    get_current_user,
    get_tenant_context,
    require_admin,
    require_owner,
)
from app.core.exceptions import (
    ResourceAlreadyExistsError,
    TenantNotFoundError,
)
from app.core.security import check_role_permission
from app.infrastructure.db.session import get_db
from app.domain.models.tenant import Tenant, UserTenantRole
from app.domain.models.user import User
from app.schemas.tenant_schema import (
    TenantCreate,
    TenantMemberAdd,
    TenantMemberResponse,
    TenantResponse,
    TenantUpdate,
)

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.post(
    "",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create tenant",
    description="Create a new tenant. The creator becomes the owner.",
)
def create_tenant(
    request: TenantCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Create a new tenant.

    Args:
        request: Tenant creation data
        current_user: Current user (becomes owner)
        db: Database session

    Returns:
        Created tenant

    Raises:
        HTTPException: If tenant name already exists
    """
    # Check if name already exists
    existing = db.query(Tenant).filter(Tenant.name == request.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant name already exists: {request.name}",
        )

    # Create tenant
    tenant = Tenant(
        name=request.name,
        description=request.description,
        settings=request.settings or {},
    )
    db.add(tenant)
    db.flush()

    # Add creator as owner
    owner_role = UserTenantRole(
        user_id=str(current_user.id),
        tenant_id=str(tenant.id),
        role="owner",
    )
    db.add(owner_role)

    db.commit()
    db.refresh(tenant)

    return TenantResponse(
        id=str(tenant.id),
        name=tenant.name,
        description=tenant.description,
        settings=tenant.settings,
        billing_status=tenant.billing_status,
        created_at=tenant.created_at,
    )


@router.get(
    "",
    response_model=list[TenantResponse],
    summary="List user's tenants",
    description="List all tenants the current user is a member of.",
)
def list_tenants(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """List user's tenants.

    Args:
        current_user: Current user
        db: Database session

    Returns:
        List of tenants
    """
    # Get user's tenant roles
    roles = (
        db.query(UserTenantRole)
        .filter(UserTenantRole.user_id == current_user.id)
        .all()
    )

    tenant_ids = [r.tenant_id for r in roles]

    if not tenant_ids:
        return []

    tenants = db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).all()

    return [
        TenantResponse(
            id=str(t.id),
            name=t.name,
            description=t.description,
            settings=t.settings,
            billing_status=t.billing_status,
            created_at=t.created_at,
        )
        for t in tenants
    ]


@router.get(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Get tenant details",
    description="Get tenant details. Requires membership.",
)
def get_tenant(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Get tenant details.

    Args:
        ctx: Tenant context
        db: Database session

    Returns:
        Tenant details
    """
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    return TenantResponse(
        id=str(tenant.id),
        name=tenant.name,
        description=tenant.description,
        settings=tenant.settings,
        billing_status=tenant.billing_status,
        created_at=tenant.created_at,
    )


@router.patch(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Update tenant",
    description="Update tenant details. Requires owner role.",
)
def update_tenant(
    request: TenantUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Update tenant details.

    Args:
        request: Update data
        ctx: Tenant context
        _: Owner role check
        db: Database session

    Returns:
        Updated tenant
    """
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Update fields
    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(tenant, key, value)

    db.commit()
    db.refresh(tenant)

    return TenantResponse(
        id=str(tenant.id),
        name=tenant.name,
        description=tenant.description,
        settings=tenant.settings,
        billing_status=tenant.billing_status,
        created_at=tenant.created_at,
    )


@router.delete(
    "/{tenant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete tenant",
    description="Delete tenant and all associated data. Requires owner role.",
)
def delete_tenant(
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Delete tenant.

    Args:
        ctx: Tenant context
        _: Owner role check
        db: Database session
    """
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Delete all related data (cascade should handle this)
    db.delete(tenant)
    db.commit()


@router.get(
    "/{tenant_id}/members",
    response_model=list[TenantMemberResponse],
    summary="List tenant members",
    description="List all members of a tenant. Requires admin role.",
)
def list_members(
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List tenant members.

    Args:
        ctx: Tenant context
        _: Admin role check
        db: Database session

    Returns:
        List of members with roles
    """
    roles = (
        db.query(UserTenantRole)
        .filter(UserTenantRole.tenant_id == ctx.tenant_id)
        .all()
    )

    members = []
    for role in roles:
        user = db.query(User).filter(User.id == role.user_id).first()
        if user:
            members.append(
                TenantMemberResponse(
                    user_id=str(user.id),
                    email=user.email,
                    full_name=user.full_name,
                    role=role.role,
                    joined_at=role.created_at,
                )
            )

    return members


@router.post(
    "/{tenant_id}/members",
    response_model=TenantMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add tenant member",
    description="Add a user to the tenant. Requires admin role.",
)
def add_member(
    request: TenantMemberAdd,
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Add member to tenant.

    Args:
        request: Member data
        ctx: Tenant context
        _: Admin role check
        db: Database session

    Returns:
        Added member info

    Raises:
        HTTPException: If user not found or already member
    """
    # Find user by email
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found: {request.email}",
        )

    # Check if already member
    existing = (
        db.query(UserTenantRole)
        .filter(
            UserTenantRole.user_id == str(user.id),
            UserTenantRole.tenant_id == ctx.tenant_id,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this tenant",
        )

    # Validate role (non-owner can't add owner)
    if request.role == "owner" and ctx.role.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can add other owners",
        )

    # Create role
    role = UserTenantRole(
        user_id=str(user.id),
        tenant_id=ctx.tenant_id,
        role=request.role,
    )
    db.add(role)
    db.commit()
    db.refresh(role)

    return TenantMemberResponse(
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=role.role,
        joined_at=role.created_at,
    )


@router.patch(
    "/{tenant_id}/members/{user_id}",
    response_model=TenantMemberResponse,
    summary="Update member role",
    description="Update a member's role. Requires owner role.",
)
def update_member_role(
    user_id: str,
    role: str = Query(..., regex="^(owner|admin|viewer)$"),
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Update member's role.

    Args:
        user_id: User UUID
        role: New role
        ctx: Tenant context
        _: Owner role check
        db: Database session

    Returns:
        Updated member info

    Raises:
        HTTPException: If member not found
    """
    user_role = (
        db.query(UserTenantRole)
        .filter(
            UserTenantRole.user_id == user_id,
            UserTenantRole.tenant_id == ctx.tenant_id,
        )
        .first()
    )

    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    # Prevent removing last owner
    if user_role.role == "owner" and role != "owner":
        owner_count = (
            db.query(UserTenantRole)
            .filter(
                UserTenantRole.tenant_id == ctx.tenant_id,
                UserTenantRole.role == "owner",
            )
            .count()
        )
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last owner",
            )

    user_role.role = role
    db.commit()
    db.refresh(user_role)

    user = db.query(User).filter(User.id == user_id).first()

    return TenantMemberResponse(
        user_id=user_id,
        email=user.email if user else "",
        full_name=user.full_name if user else "",
        role=user_role.role,
        joined_at=user_role.created_at,
    )


@router.delete(
    "/{tenant_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove member",
    description="Remove a member from the tenant. Requires admin role.",
)
def remove_member(
    user_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Remove member from tenant.

    Args:
        user_id: User UUID
        ctx: Tenant context
        _: Admin role check
        db: Database session

    Raises:
        HTTPException: If member not found or removing self
    """
    # Cannot remove yourself
    if user_id == str(ctx.user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove yourself",
        )

    user_role = (
        db.query(UserTenantRole)
        .filter(
            UserTenantRole.user_id == user_id,
            UserTenantRole.tenant_id == ctx.tenant_id,
        )
        .first()
    )

    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    # Only owner can remove other owners
    if user_role.role == "owner" and ctx.role.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can remove other owners",
        )

    # Prevent removing last owner
    if user_role.role == "owner":
        owner_count = (
            db.query(UserTenantRole)
            .filter(
                UserTenantRole.tenant_id == ctx.tenant_id,
                UserTenantRole.role == "owner",
            )
            .count()
        )
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last owner",
            )

    db.delete(user_role)
    db.commit()
