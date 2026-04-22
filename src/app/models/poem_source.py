from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db.database import Base
from ..core.enums import PoemSourceStatus

__all__ = ["PoemSource", "PoemSourceStatus"]


class PoemSource(Base):
    __tablename__ = "poem_source"

    id: Mapped[int] = mapped_column("id", autoincrement=True, nullable=False, unique=True, primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    media_path: Mapped[str | None] = mapped_column(String, default=None)
    enhance: Mapped[str | None] = mapped_column(String(500), default=None)
    status: Mapped[str] = mapped_column(String, default=PoemSourceStatus.PROCESSING.value, index=True)
    image_analysis: Mapped[str | None] = mapped_column(Text, default=None)
    follow_up_questions: Mapped[list[dict[str, str]] | None] = mapped_column(JSON, default=None)
    follow_up_answers: Mapped[dict[str, str] | None] = mapped_column(JSON, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default_factory=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    is_deleted: Mapped[bool] = mapped_column(default=False, index=True)
