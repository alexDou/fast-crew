"""Storage service with local and S3 backends for media and output artifacts."""

from __future__ import annotations

import asyncio
import mimetypes
import tempfile
import uuid
from pathlib import Path
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import UploadFile

from ..core.config import settings


class StorageError(RuntimeError):
    """Raised when storage operations fail."""


class StorageService:
    """Read/write helper for media and generated output artifacts."""

    def __init__(self) -> None:
        self._s3_client: BaseClient | None = None

    @property
    def is_s3_backend(self) -> bool:
        return settings.STORAGE_BACKEND.strip().lower() == "s3"

    def build_media_object_key(self, username: str, file_extension: str) -> str:
        """Build a deterministic media key/path for an uploaded file."""
        safe_username = "".join(char for char in username if char.isalnum() or char in {"-", "_"}) or "user"
        media_prefix = settings.S3_MEDIA_PREFIX.strip("/")
        return f"{media_prefix}/{safe_username}/{uuid.uuid4()}{file_extension}"

    async def upload_source_file(self, file: UploadFile, object_key: str) -> str:
        """Upload a FastAPI UploadFile and return the stored path reference."""
        if self.is_s3_backend:
            return await asyncio.to_thread(self._upload_file_to_s3, file, object_key)
        return await asyncio.to_thread(self._upload_file_to_local, file, object_key)

    def resolve_media_url(self, media_path: str | None) -> str | None:
        """Convert stored media path to a URL consumable by the UI."""
        if not media_path:
            return None

        if media_path.startswith("http://") or media_path.startswith("https://"):
            return media_path

        if media_path.startswith("s3://"):
            bucket, object_key = self._parse_s3_uri(media_path)
            return self._generate_presigned_url(bucket=bucket, object_key=object_key)

        # Local filesystem path exposed by Nginx as /media/... in production.
        return f"/{media_path.lstrip('/')}"

    def attach_media_url(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return payload with media_path transformed to a browser URL."""
        normalized = dict(payload)
        normalized["media_path"] = self.resolve_media_url(payload.get("media_path"))
        return normalized

    def prepare_local_media_file(self, media_path: str) -> tuple[str, bool]:
        """Return a local file path for processing.

        Returns `(path, should_cleanup)`.
        """
        if media_path.startswith("s3://"):
            bucket, object_key = self._parse_s3_uri(media_path)
            suffix = Path(object_key).suffix

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_path = temp_file.name

            try:
                self._get_s3_client().download_file(bucket, object_key, temp_path)
            except (BotoCoreError, ClientError) as exc:
                raise StorageError(f"Failed to download media from S3: {exc}") from exc

            return temp_path, True

        local_path = self._resolve_local_path(media_path)
        if not local_path.exists():
            raise StorageError(f"Local media file not found: {local_path}")

        return str(local_path), False

    def delete_media(self, media_path: str) -> None:
        """Delete uploaded media file/object."""
        if media_path.startswith("s3://"):
            bucket, object_key = self._parse_s3_uri(media_path)
            try:
                self._get_s3_client().delete_object(Bucket=bucket, Key=object_key)
            except (BotoCoreError, ClientError) as exc:
                raise StorageError(f"Failed to delete S3 media object: {exc}") from exc
            return

        local_path = self._resolve_local_path(media_path)
        if local_path.exists():
            local_path.unlink()

    def store_output_artifact(self, poem_source_id: int, filename: str, content: str) -> str:
        """Persist generated output artifact to storage and return stored path."""
        output_prefix = settings.S3_OUTPUT_PREFIX.strip("/")
        object_key = f"{output_prefix}/{poem_source_id}/{filename}"

        if self.is_s3_backend:
            if not settings.S3_BUCKET_NAME:
                raise StorageError("S3_BUCKET_NAME must be set when STORAGE_BACKEND=s3")

            try:
                self._get_s3_client().put_object(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=object_key,
                    Body=content.encode("utf-8"),
                    ContentType="text/markdown; charset=utf-8",
                )
            except (BotoCoreError, ClientError) as exc:
                raise StorageError(f"Failed to upload output artifact to S3: {exc}") from exc

            return f"s3://{settings.S3_BUCKET_NAME}/{object_key}"

        output_path = self._resolve_local_path(object_key)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        return object_key

    def _upload_file_to_local(self, file: UploadFile, object_key: str) -> str:
        target_path = self._resolve_local_path(object_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            file.file.seek(0)
            with open(target_path, "wb") as target_file:
                while True:
                    chunk = file.file.read(1024 * 1024)
                    if not chunk:
                        break
                    target_file.write(chunk)
        except OSError as exc:
            raise StorageError(f"Failed to save file locally: {exc}") from exc

        return object_key

    def _upload_file_to_s3(self, file: UploadFile, object_key: str) -> str:
        if not settings.S3_BUCKET_NAME:
            raise StorageError("S3_BUCKET_NAME must be set when STORAGE_BACKEND=s3")

        guessed_content_type = mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
        content_type = file.content_type or guessed_content_type

        try:
            file.file.seek(0)
            self._get_s3_client().upload_fileobj(
                file.file,
                settings.S3_BUCKET_NAME,
                object_key,
                ExtraArgs={"ContentType": content_type},
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"Failed to upload file to S3: {exc}") from exc

        return f"s3://{settings.S3_BUCKET_NAME}/{object_key}"

    def _resolve_local_path(self, relative_path: str) -> Path:
        storage_root = Path(settings.LOCAL_STORAGE_ROOT).expanduser().resolve()
        return storage_root / relative_path.lstrip("/")

    def _generate_presigned_url(self, bucket: str, object_key: str) -> str:
        try:
            return str(self._get_s3_client().generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": bucket, "Key": object_key},
                ExpiresIn=settings.S3_SIGNED_URL_EXPIRE_SECONDS,
            ))
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"Failed to generate pre-signed URL for media object: {exc}") from exc

    def _parse_s3_uri(self, media_path: str) -> tuple[str, str]:
        without_scheme = media_path[len("s3://") :]
        bucket, _, object_key = without_scheme.partition("/")

        if not bucket or not object_key:
            raise StorageError(f"Invalid S3 URI: {media_path}")

        return bucket, object_key

    def _get_s3_client(self) -> BaseClient:
        if self._s3_client is not None:
            return self._s3_client

        if not self.is_s3_backend:
            raise StorageError("S3 client requested while STORAGE_BACKEND is not set to s3")

        session_kwargs: dict[str, str] = {}
        if settings.AWS_PROFILE:
            session_kwargs["profile_name"] = settings.AWS_PROFILE

        session = boto3.session.Session(**session_kwargs)

        client_kwargs: dict[str, str] = {
            "service_name": "s3",
            "region_name": settings.S3_REGION,
        }

        if settings.S3_ENDPOINT_URL:
            client_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL

        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            client_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
            client_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY

            if settings.AWS_SESSION_TOKEN:
                client_kwargs["aws_session_token"] = settings.AWS_SESSION_TOKEN

        self._s3_client = session.client(**client_kwargs)
        return self._s3_client


storage_service = StorageService()
