"""API tokens for machines.

The RTTS automation alone wrote 1332 runs into TestRail. None of that can
move across until a CI job can authenticate without a browser session, so a
token is not a nice-to-have -- it is the thing that lets the old jobs keep
working against the new system.

Only a hash is stored; the plaintext is shown once, at creation.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ApiToken(Base, TimestampMixin):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # sha256 of the token; lookup is by the public prefix, not by scanning
    prefix: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
