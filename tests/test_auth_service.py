"""Unit tests for authentication service."""

import uuid

import pytest

from app.core.exceptions import InvalidCredentialsError, UserNotFoundError
from app.core.security import get_password_hash, verify_password
from app.domain.models.user import User
from app.schemas.auth_schema import UserRegisterRequest
from app.application.auth_service import AuthService


# ============================================================================
# User Registration Tests
# ============================================================================


class TestUserRegistration:
    """Tests for user registration."""

    def test_register_new_user(self, db_session):
        """Test registering a new user successfully."""
        auth_service = AuthService(db_session)

        data = UserRegisterRequest(
            email="newuser@example.com",
            password="StrongPass123",
            full_name="New User",
        )

        user = auth_service.register_user(data)

        assert user is not None
        assert user.email == "newuser@example.com"
        assert user.full_name == "New User"
        assert user.is_active is True
        assert user.password_hash is not None
        assert user.password_hash != "StrongPass123"  # Should be hashed

    def test_register_duplicate_email(self, db_session, test_user):
        """Test registering with existing email raises error."""
        auth_service = AuthService(db_session)

        data = UserRegisterRequest(
            email=test_user.email,
            password="AnotherPass123",
            full_name="Duplicate User",
        )

        with pytest.raises(ValueError, match="Email already registered"):
            auth_service.register_user(data)

    def test_register_stores_hashed_password(self, db_session):
        """Test that password is stored hashed, not plain text."""
        auth_service = AuthService(db_session)
        password = "SecurePass456"

        data = UserRegisterRequest(
            email="hashtest@example.com",
            password=password,
            full_name="Hash Test",
        )

        user = auth_service.register_user(data)

        assert user.password_hash != password
        assert verify_password(password, user.password_hash) is True

    def test_register_user_has_uuid(self, db_session):
        """Test that registered user gets a UUID id."""
        auth_service = AuthService(db_session)

        data = UserRegisterRequest(
            email="uuid_test@example.com",
            password="StrongPass123",
            full_name="UUID Test",
        )

        user = auth_service.register_user(data)

        assert user.id is not None


# ============================================================================
# User Authentication Tests
# ============================================================================


class TestUserAuthentication:
    """Tests for user authentication."""

    def test_authenticate_valid_credentials(self, db_session, test_user):
        """Test authentication with valid credentials."""
        auth_service = AuthService(db_session)

        user = auth_service.authenticate_user(
            email="testuser@example.com",
            password="StrongPass123",
        )

        assert user is not None
        assert user.email == "testuser@example.com"
        assert user.id == test_user.id

    def test_authenticate_wrong_password(self, db_session, test_user):
        """Test authentication with wrong password raises error."""
        auth_service = AuthService(db_session)

        with pytest.raises(InvalidCredentialsError):
            auth_service.authenticate_user(
                email="testuser@example.com",
                password="WrongPassword999",
            )

    def test_authenticate_nonexistent_email(self, db_session):
        """Test authentication with non-existent email raises error."""
        auth_service = AuthService(db_session)

        with pytest.raises(InvalidCredentialsError):
            auth_service.authenticate_user(
                email="nobody@example.com",
                password="SomePass123",
            )

    def test_authenticate_inactive_user(self, db_session, inactive_user):
        """Test authentication with inactive user raises error."""
        auth_service = AuthService(db_session)

        with pytest.raises(InvalidCredentialsError):
            auth_service.authenticate_user(
                email="inactive@example.com",
                password="StrongPass123",
            )


# ============================================================================
# Token Generation Tests
# ============================================================================


class TestTokenGeneration:
    """Tests for token generation."""

    def test_create_token_for_user(self, db_session, test_user):
        """Test creating a token for a user."""
        auth_service = AuthService(db_session)

        result = auth_service.create_token_for_user(test_user)

        assert "access_token" in result
        assert result["token_type"] == "bearer"
        assert result["expires_in"] > 0
        assert len(result["access_token"]) > 0

    def test_token_contains_user_id(self, db_session, test_user):
        """Test that token contains user ID as subject."""
        from app.core.security import get_token_subject

        auth_service = AuthService(db_session)
        result = auth_service.create_token_for_user(test_user)

        subject = get_token_subject(result["access_token"])
        assert subject == str(test_user.id)


# ============================================================================
# User Lookup Tests
# ============================================================================


class TestUserLookup:
    """Tests for user lookup methods."""

    def test_get_user_by_id(self, db_session, test_user):
        """Test getting user by ID."""
        auth_service = AuthService(db_session)

        user = auth_service.get_user_by_id(test_user.id)

        assert user is not None
        assert user.id == test_user.id
        assert user.email == test_user.email

    def test_get_user_by_id_not_found(self, db_session):
        """Test getting non-existent user by ID raises error."""
        auth_service = AuthService(db_session)
        fake_id = uuid.uuid4()

        with pytest.raises(UserNotFoundError):
            auth_service.get_user_by_id(fake_id)

    def test_get_user_by_email(self, db_session, test_user):
        """Test getting user by email."""
        auth_service = AuthService(db_session)

        user = auth_service.get_user_by_email("testuser@example.com")

        assert user is not None
        assert user.email == "testuser@example.com"

    def test_get_user_by_email_not_found(self, db_session):
        """Test getting non-existent user by email returns None."""
        auth_service = AuthService(db_session)

        user = auth_service.get_user_by_email("nobody@example.com")

        assert user is None
