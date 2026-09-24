"""The test-case library: suites, sections, cases, steps, labels, history."""
from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, DateTime, ForeignKey, Index,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, LegacyIdMixin, TimestampMixin


class Suite(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "suites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_master: Mapped[bool] = mapped_column(Boolean, default=False)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Section(Base, LegacyIdMixin, TimestampMixin):
    """Folder in the case tree. Self-referencing; TestRail nests these deeply
    (one DGPays suite has 909 sections)."""
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    suite_id: Mapped[int] = mapped_column(
        ForeignKey("suites.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    # cases.section_id cascades, so a physical delete here would take the
    # cases with it and rewrite the history of every run that executed them
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False,
                                             nullable=False, index=True)

    children: Mapped[list["Section"]] = relationship(back_populates="parent")
    parent: Mapped["Section | None"] = relationship(
        back_populates="children", remote_side="Section.id")


class Case(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "cases"
    __table_args__ = (
        Index("ix_cases_section_order", "section_id", "display_order"),
        # trigram/full-text search on the title is added in a migration
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), index=True)
    suite_id: Mapped[int] = mapped_column(
        ForeignKey("suites.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)

    template_id: Mapped[int | None] = mapped_column(ForeignKey("templates.id"))
    type_id: Mapped[int | None] = mapped_column(ForeignKey("case_types.id"))
    priority_id: Mapped[int | None] = mapped_column(ForeignKey("priorities.id"))
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="SET NULL"))

    refs: Mapped[str | None] = mapped_column(String(1000))
    estimate: Mapped[str | None] = mapped_column(String(50))
    estimate_forecast: Mapped[str | None] = mapped_column(String(50))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # every custom_* field keyed by system_name; definitions live in
    # custom_fields, values live here so adding a field needs no migration
    custom: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    steps: Mapped[list["CaseStep"]] = relationship(
        back_populates="case", cascade="all, delete-orphan",
        order_by="CaseStep.idx")


class CaseStep(Base):
    """One row of custom_steps_separated, promoted out of JSON because steps
    are edited, reordered and reported on individually."""
    __tablename__ = "case_steps"
    __table_args__ = (UniqueConstraint("case_id", "idx"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    expected: Mapped[str | None] = mapped_column(Text)
    additional_info: Mapped[str | None] = mapped_column(Text)
    refs: Mapped[str | None] = mapped_column(String(1000))
    # set when the step is a reference to a shared step
    shared_step_id: Mapped[int | None] = mapped_column(BigInteger)

    case: Mapped[Case] = relationship(back_populates="steps")


class Label(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "labels"
    __table_args__ = (UniqueConstraint("project_id", "title"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)


class CaseLabel(Base):
    __tablename__ = "case_labels"
    __table_args__ = (UniqueConstraint("case_id", "label_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    label_id: Mapped[int] = mapped_column(
        ForeignKey("labels.id", ondelete="CASCADE"), index=True)


class SharedStep(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "shared_steps"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CaseHistory(Base):
    """Append-only change log, seeded from TestRail's own history export and
    then written by the application itself."""
    __tablename__ = "case_history"
    __table_args__ = (Index("ix_case_history_case_time", "case_id", "created_on"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    # [{field, old_text, new_text}, ...] exactly as TestRail records it
    changes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(20), default="testrail")
