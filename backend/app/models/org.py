"""People, permissions and projects."""
from datetime import datetime

from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, LegacyIdMixin, TimestampMixin


class Role(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_project_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # coarse capability flags, expanded from TestRail's fixed role set
    permissions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class User(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False,
                                       index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"))
    # null for SSO-only accounts
    password_hash: Mapped[str | None] = mapped_column(String(255))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    role: Mapped[Role | None] = relationship()


class Group(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


class Project(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    announcement: Mapped[str | None] = mapped_column(Text)
    show_announcement: Mapped[bool] = mapped_column(Boolean, default=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 1=single suite, 2=single+baselines, 3=multi-suite (all DGPays projects are 3)
    suite_mode: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # TestRail's "Default Access": the role everyone without a membership of
    # their own (or through a group) holds here. Null is "global role" --
    # people get whatever their global role gives them, which is how every
    # project came across. The No Access role closes the project to all but
    # its members.
    default_role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"))


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"))


class ProjectGroup(Base):
    """A group's role in one project.

    Precedence follows TestRail: a person's own membership wins; failing
    that, the groups they belong to count, and across several groups the
    capabilities add up; failing that, the project's default access.
    """
    __tablename__ = "project_groups"
    __table_args__ = (UniqueConstraint("project_id", "group_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)


class PasswordToken(Base):
    """A single-use link for setting a password: an invitation or a reset.

    Only the SHA-256 of the token is stored. The link itself goes to the
    person (or to the administrator, when there is no mail server), so a
    copy of this table is not a set of working links.
    """
    __tablename__ = "password_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # invite | reset
    purpose: Mapped[str] = mapped_column(String(10), nullable=False)
    created_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
