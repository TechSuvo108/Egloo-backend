from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
from app.database import Base


class DataSource(Base):
    __tablename__ = "data_sources"

    __table_args__ = (
        UniqueConstraint("user_id", "source_type", name="uq_user_source_type"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type = Column(String, nullable=False)
    # values: "gmail" | "slack" | "google_drive"

    access_token = Column(String, nullable=True)
    # encrypted with Fernet before storing

    refresh_token = Column(String, nullable=True)
    # encrypted with Fernet before storing

    token_expiry = Column(DateTime(timezone=True), nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    sync_status = Column(String, default="idle")
    # values: "idle" | "syncing" | "success" | "error"

    source_metadata = Column(JSONB, nullable=True)
    # optional: store team_name for Slack, scopes, etc.

    created_at = Column(DateTime(timezone=True), server_default=func.now())
