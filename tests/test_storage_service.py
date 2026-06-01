from src.app.core.config import settings
from src.app.services.storage_service import StorageService


def test_resolve_media_url_for_local_path() -> None:
    service = StorageService()

    assert service.resolve_media_url("media/alice/photo.jpg") == "/media/alice/photo.jpg"


def test_resolve_media_url_for_s3_path(monkeypatch) -> None:
    service = StorageService()

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "s3")

    def _fake_presigned_url(bucket: str, object_key: str) -> str:
        return f"https://signed.example/{bucket}/{object_key}"

    monkeypatch.setattr(service, "_generate_presigned_url", _fake_presigned_url)

    resolved = service.resolve_media_url("s3://aisee-bucket/media/alice/photo.jpg")

    assert resolved == "https://signed.example/aisee-bucket/media/alice/photo.jpg"


def test_build_media_object_key_sanitizes_username(monkeypatch) -> None:
    service = StorageService()

    monkeypatch.setattr(settings, "S3_MEDIA_PREFIX", "media")

    key = service.build_media_object_key("alice***", ".png")

    assert key.startswith("media/alice/")
    assert key.endswith(".png")


def test_store_output_artifact_to_local_disk(monkeypatch, tmp_path) -> None:
    service = StorageService()

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "S3_OUTPUT_PREFIX", "output")

    stored_path = service.store_output_artifact(poem_source_id=8, filename="poem.md", content="Great poem")

    assert stored_path == "output/8/poem.md"
    assert (tmp_path / stored_path).read_text(encoding="utf-8") == "Great poem"
