from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
import enum

from ..core.db.database import Base


class PoemSourceStatus(str, enum.Enum):
    """Status of poem generation processing."""
    PROCESSING = "processing"
    SUCCESS = "success"
    ERROR = "error"


class PoemSource(Base):
    __tablename__ = "poem_source"

    id: Mapped[int] = mapped_column("id", autoincrement=True, nullable=False, unique=True, primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    media_path: Mapped[str | None] = mapped_column(String, default=None)
    enhance: Mapped[str | None] = mapped_column(String(500), default=None)
    status: Mapped[str] = mapped_column(String, default="processing", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default_factory=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    is_deleted: Mapped[bool] = mapped_column(default=False, index=True)
