"""Unit tests for core security module."""

from datetime import timedelta

import pytest

from app.core.security import (
    ROLE_HIERARCHY,
    check_role_permission,
    create_access_token,
    decode_token,
    get_password_hash,
    get_token_subject,
    verify_password,
)


# ============================================================================
# Password Hashing Tests
# ============================================================================


class TestPasswordHashing:
    """Tests for password hashing and verification."""

    def test_hash_password(self):
        """Test that password hashing produces a hash."""
        password = "SecurePassword123"
        hashed = get_password_hash(password)

        assert hashed is not None
        assert hashed != password
        assert len(hashed) > 0

    def test_verify_correct_password(self):
        """Test verifying a correct password."""
        password = "SecurePassword123"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self):
        """Test verifying an incorrect password."""
        password = "SecurePassword123"
        hashed = get_password_hash(password)

        assert verify_password("WrongPassword456", hashed) is False

    def test_different_hashes_for_same_password(self):
        """Test that same password produces different hashes (bcrypt salt)."""
        password = "SecurePassword123"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != hash2  # Different salts
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True

    def test_empty_password(self):
        """Test hashing empty password still works."""
        hashed = get_password_hash("")
        assert verify_password("", hashed) is True
        assert verify_password("notempty", hashed) is False


# ============================================================================
# JWT Token Tests
# ============================================================================


class TestJWTTokens:
    """Tests for JWT token creation and validation."""

    def test_create_access_token(self):
        """Test creating a valid access token."""
        token = create_access_token(subject="user-123")

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_valid_token(self):
        """Test decoding a valid token returns correct payload."""
        user_id = "test-user-uuid-123"
        token = create_access_token(subject=user_id)

        payload = decode_token(token)

        assert payload is not None
        assert payload["sub"] == user_id
        assert "exp" in payload
        assert "iat" in payload

    def test_get_token_subject(self):
        """Test extracting subject from token."""
        user_id = "user-abc-456"
        token = create_access_token(subject=user_id)

        subject = get_token_subject(token)

        assert subject == user_id

    def test_decode_invalid_token(self):
        """Test decoding an invalid token returns None."""
        payload = decode_token("invalid.token.string")

        assert payload is None

    def test_get_subject_invalid_token(self):
        """Test extracting subject from invalid token returns None."""
        subject = get_token_subject("totally-not-a-valid-jwt")

        assert subject is None

    def test_token_with_custom_expiration(self):
        """Test token with custom expiration time."""
        token = create_access_token(
            subject="user-123",
            expires_delta=timedelta(hours=2),
        )

        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"

    def test_token_with_extra_claims(self):
        """Test token with extra claims."""
        token = create_access_token(
            subject="user-123",
            extra_claims={"role": "admin", "tenant_id": "t-456"},
        )

        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["role"] == "admin"
        assert payload["tenant_id"] == "t-456"

    def test_expired_token(self):
        """Test that expired token is rejected."""
        token = create_access_token(
            subject="user-123",
            expires_delta=timedelta(seconds=-1),  # Already expired
        )

        payload = decode_token(token)
        assert payload is None


# ============================================================================
# RBAC Tests
# ============================================================================


class TestRBAC:
    """Tests for role-based access control."""

    def test_role_hierarchy_exists(self):
        """Test that role hierarchy is properly defined."""
        assert "owner" in ROLE_HIERARCHY
        assert "admin" in ROLE_HIERARCHY
        assert "viewer" in ROLE_HIERARCHY

    def test_owner_has_highest_level(self):
        """Test that owner has the highest privilege level."""
        assert ROLE_HIERARCHY["owner"] > ROLE_HIERARCHY["admin"]
        assert ROLE_HIERARCHY["owner"] > ROLE_HIERARCHY["viewer"]

    def test_admin_above_viewer(self):
        """Test that admin is above viewer."""
        assert ROLE_HIERARCHY["admin"] > ROLE_HIERARCHY["viewer"]

    def test_owner_can_do_everything(self):
        """Test owner has access to all role levels."""
        assert check_role_permission("owner", "owner") is True
        assert check_role_permission("owner", "admin") is True
        assert check_role_permission("owner", "viewer") is True

    def test_admin_permissions(self):
        """Test admin has admin and viewer access."""
        assert check_role_permission("admin", "owner") is False
        assert check_role_permission("admin", "admin") is True
        assert check_role_permission("admin", "viewer") is True

    def test_viewer_permissions(self):
        """Test viewer only has viewer access."""
        assert check_role_permission("viewer", "owner") is False
        assert check_role_permission("viewer", "admin") is False
        assert check_role_permission("viewer", "viewer") is True

    def test_unknown_role(self):
        """Test unknown role has no permissions."""
        assert check_role_permission("unknown", "viewer") is False
        assert check_role_permission("unknown", "admin") is False
        assert check_role_permission("unknown", "owner") is False

    def test_unknown_required_role(self):
        """Test checking against unknown required role."""
        assert check_role_permission("owner", "superadmin") is True  # owner level > 0
