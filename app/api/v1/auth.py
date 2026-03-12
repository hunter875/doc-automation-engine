"""Authentication API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.exceptions import (
    AuthenticationError,
    ResourceAlreadyExistsError,
)
from app.db.postgres import get_db
from app.models.user import User
from app.schemas.auth_schema import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    description="Create a new user account with email and password.",
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
):
    """Register a new user.

    Args:
        request: Registration data
        db: Database session

    Returns:
        Created user data

    Raises:
        HTTPException: If email already exists
    """
    auth_service = AuthService(db)

    try:
        user = auth_service.register_user(data=request)

        return UserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            created_at=user.created_at,
        )

    except ResourceAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User login",
    description="Authenticate user and return JWT access token.",
)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    """Authenticate user and return token.

    Args:
        request: Login credentials
        db: Database session

    Returns:
        JWT access token

    Raises:
        HTTPException: If authentication fails
    """
    auth_service = AuthService(db)

    try:
        user = auth_service.authenticate_user(
            email=request.email,
            password=request.password,
        )

        token_data = auth_service.create_token_for_user(user)

        return TokenResponse(
            access_token=token_data["access_token"],
            token_type=token_data["token_type"],
            expires_in=token_data["expires_in"],
        )

    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Get current authenticated user's profile.",
)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get current user profile.

    Args:
        current_user: Current authenticated user

    Returns:
        User profile data
    """
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh token",
    description="Get a new access token for authenticated user.",
)
def refresh_token(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Refresh access token.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        New JWT access token
    """
    auth_service = AuthService(db)
    access_token = auth_service.create_token_for_user(current_user)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
    )
