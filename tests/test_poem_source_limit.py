"""Unit tests for poem source request limit."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from src.app.api.v1.poem_source import write_poem_source
from src.app.core.exceptions.http_exceptions import ForbiddenException


class TestPoemSourceRequestLimit:
    """Test the 3-request limit on poem source creation."""

    @pytest.mark.asyncio
    async def test_request_limit_reached(self, mock_db, current_user_dict):
        """Test that creation is rejected when user has 3 successful poems."""
        mock_request = Mock()
        mock_file = Mock()
        mock_file.filename = "test.jpg"

        with patch("src.app.api.v1.poem_source.crud_poem_sources") as mock_crud:
            mock_crud.get_multi = AsyncMock(return_value={"data": [{}, {}, {}], "total_count": 3})

            with pytest.raises(HTTPException) as exc_info:
                await write_poem_source(mock_request, mock_file, None, current_user_dict, mock_db)

            assert exc_info.value.status_code == 429
            assert "maximum of 3" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_request_limit_exceeded(self, mock_db, current_user_dict):
        """Test that creation is rejected when user has more than 3 successful poems."""
        mock_request = Mock()
        mock_file = Mock()
        mock_file.filename = "test.jpg"

        with patch("src.app.api.v1.poem_source.crud_poem_sources") as mock_crud:
            mock_crud.get_multi = AsyncMock(return_value={"data": [{}, {}, {}, {}], "total_count": 4})

            with pytest.raises(HTTPException) as exc_info:
                await write_poem_source(mock_request, mock_file, None, current_user_dict, mock_db)

            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_under_limit_proceeds(self, mock_db, current_user_dict):
        """Test that creation proceeds when user has fewer than 3 successful poems."""
        mock_request = Mock()
        mock_file = Mock()
        mock_file.filename = "test.jpg"
        mock_file.read = AsyncMock(return_value=b"fake image data")
        mock_file.close = AsyncMock()

        with patch("src.app.api.v1.poem_source.crud_poem_sources") as mock_crud:
            mock_crud.get_multi = AsyncMock(return_value={"data": [{}, {}], "total_count": 2})
            mock_crud.create = AsyncMock(return_value={"id": 1, "media_path": "s3://bucket/test.jpg", "user_id": 1, "status": "processing", "created_at": "2026-01-01"})

            with patch("src.app.api.v1.poem_source.storage_service") as mock_storage:
                mock_storage.build_media_object_key.return_value = "media/test/uuid.jpg"
                mock_storage.upload_upload_file = AsyncMock(return_value="s3://bucket/test.jpg")
                mock_storage.attach_media_url.return_value = {"id": 1, "media_path": "s3://bucket/test.jpg", "media_url": "https://signed-url", "user_id": 1, "status": "processing", "created_at": "2026-01-01"}

                with patch("src.app.api.v1.poem_source.crewai_service") as mock_crew:
                    mock_crew.start_poem_generation = Mock()

                    result = await write_poem_source(mock_request, mock_file, None, current_user_dict, mock_db)

                    assert result["id"] == 1
                    mock_crud.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_zero_poems_allowed(self, mock_db, current_user_dict):
        """Test that a new user with zero poems can create one."""
        mock_request = Mock()
        mock_file = Mock()
        mock_file.filename = "test.png"
        mock_file.read = AsyncMock(return_value=b"fake image data")
        mock_file.close = AsyncMock()

        with patch("src.app.api.v1.poem_source.crud_poem_sources") as mock_crud:
            mock_crud.get_multi = AsyncMock(return_value={"data": [], "total_count": 0})
            mock_crud.create = AsyncMock(return_value={"id": 1, "media_path": "s3://b/t.png", "user_id": 1, "status": "processing", "created_at": "2026-01-01"})

            with patch("src.app.api.v1.poem_source.storage_service") as mock_storage:
                mock_storage.build_media_object_key.return_value = "media/test/uuid.png"
                mock_storage.upload_upload_file = AsyncMock(return_value="s3://b/t.png")
                mock_storage.attach_media_url.return_value = {"id": 1, "media_path": "s3://b/t.png", "media_url": "https://url", "user_id": 1, "status": "processing", "created_at": "2026-01-01"}

                with patch("src.app.api.v1.poem_source.crewai_service") as mock_crew:
                    mock_crew.start_poem_generation = Mock()

                    result = await write_poem_source(mock_request, mock_file, None, current_user_dict, mock_db)

                    assert result is not None

    @pytest.mark.asyncio
    async def test_no_current_user_forbidden(self, mock_db):
        """Test that missing current_user raises ForbiddenException."""
        mock_request = Mock()
        mock_file = Mock()
        mock_file.filename = "test.jpg"

        with pytest.raises(ForbiddenException):
            await write_poem_source(mock_request, mock_file, None, None, mock_db)
