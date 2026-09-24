"""Files attached to cases, runs, tests and results.

Two kinds arrive from TestRail and both must survive the move:

* real attachments, listed by ``get_attachments_for_*``;
* inline images pasted into rich-text fields, which appear in the text as
  ``index.php?/attachments/get/<id>``. Those URLs stop resolving the moment the
  TestRail subscription ends, so the loader rewrites every one of them to point
  at our own ``/api/attachments/<id>`` route.
"""
from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, DateTime, ForeignKey, Index,
                        Integer, String)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Attachment(Base, TimestampMixin):
    __tablename__ = "attachments"
    __table_args__ = (
        Index("ix_attachments_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # TestRail attachment ids are UUID strings on newer instances, ints on old
    testrail_id: Mapped[str | None] = mapped_column(String(64), unique=True,
                                                    index=True)

    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(BigInteger)

    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    size: Mapped[int | None] = mapped_column(BigInteger)
    content_type: Mapped[str | None] = mapped_column(String(200))
    # path inside the object store / mounted volume
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), index=True)

    # true when the file is referenced from inside a rich-text field rather
    # than shown in the attachment list
    is_inline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
