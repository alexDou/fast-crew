"""Unit tests for login API endpoint - email verification."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.app.api.v1.login import login_for_access_token
from src.app.core.config import settings
from src.app.core.exceptions.http_exceptions import UnauthorizedException


class TestLoginEmailVerification:
    """Test email verification gate on login."""

    @pytest.mark.asyncio
    async def test_login_unverified_email_rejected(self, mock_db):
        """Test that login is rejected when email is not verified."""
        mock_response = Mock()
        mock_form = Mock()
        mock_form.username = "testuser"
        mock_form.password = "testpass"

        unverified_user = {
            "id": 1,
            "username": "testuser",
            "email": "test@test.com",
            "is_email_verified": False,
            "hashed_password": "hashed",
        }

        with patch("src.app.api.v1.login.authenticate_user", new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = unverified_user

            with pytest.raises(UnauthorizedException, match="not yet verified"):
                await login_for_access_token(mock_response, mock_form, mock_db)

    @pytest.mark.asyncio
    async def test_login_verified_email_succeeds(self, mock_db):
        """Test that login succeeds when email is verified."""
        mock_response = Mock()
        mock_form = Mock()
        mock_form.username = "testuser"
        mock_form.password = "testpass"

        verified_user = {
            "id": 1,
            "username": "testuser",
            "email": "test@test.com",
            "is_email_verified": True,
            "hashed_password": "hashed",
        }

        with patch("src.app.api.v1.login.authenticate_user", new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = verified_user

            with patch("src.app.api.v1.login.create_access_token", new_callable=AsyncMock) as mock_access:
                mock_access.return_value = "access_token_value"

                with patch("src.app.api.v1.login.create_refresh_token", new_callable=AsyncMock) as mock_refresh:
                    mock_refresh.return_value = "refresh_token_value"

                    result = await login_for_access_token(mock_response, mock_form, mock_db)

                    assert result["access_token"] == "access_token_value"
                    assert result["token_type"] == "bearer"
                    mock_response.set_cookie.assert_called_once()
                    assert mock_response.set_cookie.call_args.kwargs["secure"] == settings.SESSION_SECURE_COOKIES

    @pytest.mark.asyncio
    async def test_login_wrong_credentials(self, mock_db):
        """Test that login fails with wrong credentials."""
        mock_response = Mock()
        mock_form = Mock()
        mock_form.username = "testuser"
        mock_form.password = "wrongpass"

        with patch("src.app.api.v1.login.authenticate_user", new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = False

            with pytest.raises(UnauthorizedException, match="Wrong username"):
                await login_for_access_token(mock_response, mock_form, mock_db)
