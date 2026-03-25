"""Unit tests for email verification endpoints."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastcrud.exceptions.http_exceptions import NotFoundException

from src.app.api.v1.users import resend_verification, verify_email, write_user
from src.app.schemas.user import ResendVerificationRequest, UserCreate


class TestVerifyEmail:
    """Test email verification endpoint."""

    @pytest.mark.asyncio
    async def test_verify_email_success(self, mock_db):
        """Test successful email verification."""
        mock_request = Mock()
        token_payload = {"sub": "test@test.com", "purpose": "email_verification", "exp": 9999999999}

        with patch("src.app.api.v1.users.jwt") as mock_jwt:
            mock_jwt.decode.return_value = token_payload

            with patch("src.app.api.v1.users.crud_users") as mock_crud:
                mock_crud.get = AsyncMock(return_value={
                    "username": "testuser",
                    "email": "test@test.com",
                    "is_email_verified": False,
                })
                mock_crud.update = AsyncMock()

                mock_db.execute = AsyncMock()
                mock_db.commit = AsyncMock()

                result = await verify_email(mock_request, "valid_token", mock_db)

                assert result["message"] == "Email verified successfully. You can now log in."
                mock_db.execute.assert_called_once()
                mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_email_already_verified(self, mock_db):
        """Test verification when email is already verified."""
        mock_request = Mock()
        token_payload = {"sub": "test@test.com", "purpose": "email_verification", "exp": 9999999999}

        with patch("src.app.api.v1.users.jwt") as mock_jwt:
            mock_jwt.decode.return_value = token_payload

            with patch("src.app.api.v1.users.crud_users") as mock_crud:
                mock_crud.get = AsyncMock(return_value={
                    "username": "testuser",
                    "email": "test@test.com",
                    "is_email_verified": True,
                })

                result = await verify_email(mock_request, "valid_token", mock_db)

                assert result["message"] == "Email already verified"

    @pytest.mark.asyncio
    async def test_verify_email_invalid_token(self, mock_db):
        """Test verification with invalid/expired token."""
        mock_request = Mock()

        with patch("src.app.api.v1.users.jwt") as mock_jwt:
            from jose import JWTError
            mock_jwt.decode.side_effect = JWTError("expired")

            with pytest.raises(NotFoundException, match="Invalid or expired verification link"):
                await verify_email(mock_request, "bad_token", mock_db)

    @pytest.mark.asyncio
    async def test_verify_email_wrong_purpose(self, mock_db):
        """Test verification with token that has wrong purpose."""
        mock_request = Mock()
        token_payload = {"sub": "test@test.com", "purpose": "password_reset", "exp": 9999999999}

        with patch("src.app.api.v1.users.jwt") as mock_jwt:
            mock_jwt.decode.return_value = token_payload

            with pytest.raises(NotFoundException, match="Invalid verification link"):
                await verify_email(mock_request, "wrong_purpose_token", mock_db)

    @pytest.mark.asyncio
    async def test_verify_email_user_not_found(self, mock_db):
        """Test verification when user doesn't exist."""
        mock_request = Mock()
        token_payload = {"sub": "noone@test.com", "purpose": "email_verification", "exp": 9999999999}

        with patch("src.app.api.v1.users.jwt") as mock_jwt:
            mock_jwt.decode.return_value = token_payload

            with patch("src.app.api.v1.users.crud_users") as mock_crud:
                mock_crud.get = AsyncMock(return_value=None)

                with pytest.raises(NotFoundException, match="User not found"):
                    await verify_email(mock_request, "valid_token", mock_db)


class TestResendVerification:
    """Test resend verification endpoint."""

    @pytest.mark.asyncio
    async def test_resend_for_unverified_user(self, mock_db):
        """Test resend verification for valid unverified user."""
        mock_request = Mock()
        payload = ResendVerificationRequest(identifier="testuser")

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            mock_crud.get = AsyncMock(return_value={
                "username": "testuser",
                "email": "test@test.com",
                "is_email_verified": False,
            })

            with patch("src.app.api.v1.users.create_email_verification_token", new_callable=AsyncMock) as mock_token:
                mock_token.return_value = "new_token"
                with patch("src.app.api.v1.users._send_verification_email", new_callable=AsyncMock) as mock_sender:
                    result = await resend_verification(mock_request, payload, mock_db)

                assert "verification link has been sent" in result["message"]
                mock_token.assert_called_once()
                mock_sender.assert_called_once()

    @pytest.mark.asyncio
    async def test_resend_for_already_verified_user(self, mock_db):
        """Test resend verification for already verified user."""
        mock_request = Mock()
        payload = ResendVerificationRequest(email="test@test.com")

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            mock_crud.get = AsyncMock(return_value={
                "username": "testuser",
                "email": "test@test.com",
                "is_email_verified": True,
            })

            result = await resend_verification(mock_request, payload, mock_db)

            assert result["message"] == "Email is already verified."

    @pytest.mark.asyncio
    async def test_resend_for_nonexistent_email(self, mock_db):
        """Test resend for email that doesn't exist - should not reveal."""
        mock_request = Mock()
        payload = ResendVerificationRequest(email="noone@test.com")

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            mock_crud.get = AsyncMock(return_value=None)

            result = await resend_verification(mock_request, payload, mock_db)

            # Should NOT reveal whether the email exists
            assert "verification link has been sent" in result["message"]

    @pytest.mark.asyncio
    async def test_resend_uses_identifier_when_not_email(self, mock_db):
        """Test resend lookup by username identifier."""
        mock_request = Mock()
        payload = ResendVerificationRequest(identifier="testuser")

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            mock_crud.get = AsyncMock(return_value=None)
            await resend_verification(mock_request, payload, mock_db)
            mock_crud.get.assert_called_once_with(db=mock_db, username="testuser", is_deleted=False)


class TestWriteUserVerification:
    """Test that user registration generates verification token."""

    @pytest.mark.asyncio
    async def test_registration_generates_verification_token(self, mock_db, sample_user_data, sample_user_read):
        """Test that creating a user generates a verification token."""
        user_create = UserCreate(**sample_user_data)

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            mock_crud.get = AsyncMock(return_value=None)
            mock_crud.exists = AsyncMock(side_effect=[False, False])
            mock_crud.create = AsyncMock(return_value=sample_user_read.model_dump())

            with patch("src.app.api.v1.users.get_password_hash") as mock_hash:
                mock_hash.return_value = "hashed_password"

                with patch(
                    "src.app.api.v1.users.create_email_verification_token",
                    new_callable=AsyncMock,
                ) as mock_token:
                    mock_token.return_value = "verification_token"
                    with patch("src.app.api.v1.users._send_verification_email", new_callable=AsyncMock) as mock_sender:
                        result = await write_user(Mock(), user_create, mock_db)

                    assert result == sample_user_read.model_dump()
                    mock_token.assert_called_once_with(data={"sub": user_create.email})
                    mock_sender.assert_called_once()
