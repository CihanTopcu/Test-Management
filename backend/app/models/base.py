"""Shared SQLAlchemy declarative base and mixins."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """Row bookkeeping owned by our application, not by TestRail."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )


class LegacyIdMixin:
    """Original TestRail primary key.

    Kept for the lifetime of the product, not just the migration: existing
    automation, JMeter jobs and bug tickets refer to cases by their TestRail
    id (``C15477``), and those references must keep resolving.
    """

    testrail_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, index=True, nullable=True
    )
