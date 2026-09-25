"""Things around the test data: saved filters, notifications, audit log."""
from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, DateTime, ForeignKey, Index,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class SavedFilter(Base, TimestampMixin):
    """A named set of list criteria.

    With 5,558 cases in one project, the same three or four filters get
    retyped every morning. Shared filters let a team agree on what
    "the regression set" means instead of each person rebuilding it.
    """
    __tablename__ = "saved_filters"
    __table_args__ = (UniqueConstraint("owner_id", "project_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    suite_id: Mapped[int | None] = mapped_column(
        ForeignKey("suites.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # the query itself: section_id, type_id, priority_id, field/value, sort...
    criteria: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Notification(Base, TimestampMixin):
    """An outbox row.

    Written synchronously when something happens, delivered separately. A row
    that fails to send stays visible with its error instead of vanishing into
    an SMTP timeout, and the in-app list works whether or not mail is
    configured at all.
    """
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(String(500))

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_status: Mapped[str] = mapped_column(String(20), default="pending")
    email_error: Mapped[str | None] = mapped_column(String(400))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationPreference(Base, TimestampMixin):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id", "kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    in_app: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AuditEntry(Base):
    """Who changed what, across the whole instance.

    Case edits already have their own history, because TestRail kept one and
    the migration carried 152,872 of those rows over. This is the other half:
    the administrative changes nothing else records -- a role's capabilities
    edited, a user deactivated, a run deleted, a project's membership
    changed. Those are precisely the ones somebody asks about three months
    later, and until now the honest answer was that we did not know.
    """
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_time", "created_on"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True)
    # create | update | delete | login | export
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    # what it was called at the time, so the line still reads after a delete
    label: Mapped[str | None] = mapped_column(String(255))
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ip: Mapped[str | None] = mapped_column(String(45))


class ReportSubscription(Base, TimestampMixin):
    """A standing request for a digest by e-mail or in the app.

    People do not open a dashboard they have to remember to open. The digests
    that earn their keep are the ones that arrive: what failed overnight, and
    which milestones are about to be missed.

    Delivery is driven by the same external scheduler that flushes the mail
    queue, rather than an in-process timer -- one container, one cron entry,
    and nothing double-sends if the app restarts mid-window.
    """
    __tablename__ = "report_subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", "kind", "frequency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # null means every project the person can see
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    # summary | failures | milestones
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    # daily | weekly
    frequency: Mapped[str] = mapped_column(String(10), nullable=False,
                                           default="daily")
    # hour of day, in the server's timezone
    hour: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    # 0 = Monday; only meaningful for weekly
    weekday: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    by_email: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # what the window is measured from, and the guard against double sends
    last_sent_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True))


class SyncRun(Base):
    """One attempt at pulling changes from TestRail.

    Kept as history rather than a single "last synced" field, because the
    question people actually ask during a cut-over is "did last night's sync
    work, and what came in", and a lone timestamp cannot answer it.

    The window start is stored per run: it only moves forward when a run
    succeeds, so a failed week is re-covered by the next one instead of
    quietly falling through the gap.
    """
    __tablename__ = "sync_runs"
    __table_args__ = (Index("ix_sync_started", "started_on"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    finished_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True))
    # queued (asked for from the admin page, not yet picked up) | running |
    # ok | failed | cancelled
    status: Mapped[str] = mapped_column(String(10), nullable=False,
                                        default="running")
    # the moment this run asked TestRail to report changes from
    window_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True))
    # schedule | manual
    trigger: Mapped[str] = mapped_column(String(10), nullable=False,
                                         default="schedule")
    counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
