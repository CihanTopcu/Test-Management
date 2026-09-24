"""Execution side: milestones, plans, runs, tests, results."""
from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, DateTime, ForeignKey, Index,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, LegacyIdMixin, TimestampMixin


class Milestone(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    refs: Mapped[str | None] = mapped_column(String(1000))
    start_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_started: Mapped[bool] = mapped_column(Boolean, default=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)


class ConfigGroup(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "config_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Config(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("config_groups.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Plan(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    assignedto_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # TestRail hides archived plans from its own listing endpoint; kept as a
    # flag so they stay searchable here instead of disappearing
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False,
                                              nullable=False, index=True)


class PlanEntry(Base):
    """A plan row; one entry fans out into several runs, one per config."""
    __tablename__ = "plan_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    testrail_uuid: Mapped[str | None] = mapped_column(String(64), index=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    suite_id: Mapped[int | None] = mapped_column(
        ForeignKey("suites.id", ondelete="SET NULL"))
    name: Mapped[str | None] = mapped_column(String(255))
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class Run(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    suite_id: Mapped[int | None] = mapped_column(
        ForeignKey("suites.id", ondelete="SET NULL"), index=True)
    plan_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("plan_entries.id", ondelete="CASCADE"), index=True)
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="SET NULL"), index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    refs: Mapped[str | None] = mapped_column(String(1000))
    include_all: Mapped[bool] = mapped_column(Boolean, default=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assignedto_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # the rendered config string plus the ids it was built from
    config: Mapped[str | None] = mapped_column(String(500))
    config_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # archived runs are read-only in TestRail and invisible to get_runs; the
    # flag keeps that distinction rather than flattening it away
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False,
                                              nullable=False, index=True)

    tests: Mapped[list["Test"]] = relationship(back_populates="run")


class Test(Base, LegacyIdMixin, TimestampMixin):
    """A case instantiated into a run.

    Carries a snapshot of the case fields so that editing the case later does
    not silently rewrite what was executed.
    """
    __tablename__ = "tests"
    __table_args__ = (
        Index("ix_tests_run_case", "run_id", "case_id"),
        # the run grid and every status roll-up group by (run, status); with
        # ~1M tests after the archive import the planner otherwise scans the
        # whole table for a page that shows one run
        Index("ix_tests_run_status", "run_id", "status_id"),
        # the grid pages through one run ordered by id. Without this the
        # planner walks tests_pkey and filters, which meant 947,427 rows
        # discarded and 948ms to draw the first page of the largest run.
        Index("ix_tests_run_ordered", "run_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[int | None] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    status_id: Mapped[int | None] = mapped_column(ForeignKey("statuses.id"), index=True)
    assignedto_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    type_id: Mapped[int | None] = mapped_column(ForeignKey("case_types.id"))
    priority_id: Mapped[int | None] = mapped_column(ForeignKey("priorities.id"))
    template_id: Mapped[int | None] = mapped_column(ForeignKey("templates.id"))
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="SET NULL"))
    refs: Mapped[str | None] = mapped_column(String(1000))
    estimate: Mapped[str | None] = mapped_column(String(50))
    estimate_forecast: Mapped[str | None] = mapped_column(String(50))
    custom: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    run: Mapped[Run] = relationship(back_populates="tests")
    results: Mapped[list["Result"]] = relationship(
        back_populates="test", order_by="Result.created_on")


class Result(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "results"
    __table_args__ = (
        Index("ix_results_test_time", "test_id", "created_on"),
        # the activity report walks a date window and groups by status
        Index("ix_results_time_status", "created_on", "status_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    test_id: Mapped[int] = mapped_column(
        ForeignKey("tests.id", ondelete="CASCADE"), index=True)
    status_id: Mapped[int | None] = mapped_column(ForeignKey("statuses.id"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True)
    assignedto_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str | None] = mapped_column(String(255))
    elapsed: Mapped[str | None] = mapped_column(String(50))
    defects: Mapped[str | None] = mapped_column(String(500), index=True)
    custom: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    test: Mapped[Test] = relationship(back_populates="results")
    step_results: Mapped[list["ResultStep"]] = relationship(
        back_populates="result", cascade="all, delete-orphan",
        order_by="ResultStep.idx")


class ResultStep(Base):
    """custom_step_results: the per-step outcome of one execution."""
    __tablename__ = "result_steps"
    __table_args__ = (UniqueConstraint("result_id", "idx"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    result_id: Mapped[int] = mapped_column(
        ForeignKey("results.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    expected: Mapped[str | None] = mapped_column(Text)
    actual: Mapped[str | None] = mapped_column(Text)
    status_id: Mapped[int | None] = mapped_column(ForeignKey("statuses.id"))

    result: Mapped[Result] = relationship(back_populates="step_results")
