"""Browser scenarios written on the platform and their runs."""
from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, DateTime, ForeignKey, Index, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class AutoScenario(Base, TimestampMixin):
    """A scenario in the plain Turkish commands app/autotest/dsl.py reads.

    The free-text description it may have been drafted from is kept beside
    it, so the next person can see what the steps were meant to check.
    """
    __tablename__ = "auto_scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # a data set: header line plus rows; the scenario runs once per row
    data: Mapped[str | None] = mapped_column(Text)
    # the test case this automates: a run started from a test of that case
    # writes its outcome there as a result
    case_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("cases.id", ondelete="SET NULL"), index=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"))


class AutoRun(Base):
    """One execution of a scenario.

    The steps are copied in when the run starts: the scenario may be edited
    while it runs, or afterwards, and a run has to keep saying what it did.
    `log` is the per-step outcome the runner fills in as it goes; the page
    polls it.
    """
    __tablename__ = "auto_runs"
    __table_args__ = (Index("ix_auto_runs_scenario", "scenario_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("auto_scenarios.id", ondelete="CASCADE"), nullable=False)
    # queued | running | passed | failed | error | stopped
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="queued")
    steps: Mapped[str] = mapped_column(Text, nullable=False)
    log: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    message: Mapped[str | None] = mapped_column(Text)
    stop_requested: Mapped[bool] = mapped_column(default=False, nullable=False)
    # started from a test in a run: the outcome goes there as a result
    test_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tests.id", ondelete="SET NULL"))
    result_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("results.id", ondelete="SET NULL"))
    # part of a plan's (or a run screen's) batch
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("auto_batches.id", ondelete="SET NULL"), index=True)
    started_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"))
    created_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    started_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AutoVariable(Base, TimestampMixin):
    """A value a scenario refers to as {{NAME}}: an address, a test user, a
    password. Kept per project so the same scenario runs against another
    environment by changing one value, and so a password is not written
    into the steps. Secret values are stored encrypted, never sent back to
    the page and masked in a run's log.
    """
    __tablename__ = "auto_variables"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # plain for ordinary values, Fernet token for secrets
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"))


class AutoPlan(Base, TimestampMixin):
    """Scenarios that run by themselves on a schedule.

    The schedule is weekdays and times of day in the configured time zone:
    "weekdays at 07:30 and 13:00" is what people ask for, and it reads back
    the same way. next_run_at is kept so the scheduler only has to compare
    one column, and so the page can say when the next run is.
    """
    __tablename__ = "auto_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    scenario_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # 0 = Monday … 6 = Sunday
    days: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # "HH:MM"
    times: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # record the outcome in a new test run of the linked cases
    record_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notify_user_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # also tell them when everything passed, not only on a failure
    notify_always: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"))


class AutoBatch(Base):
    """One firing of a plan, or a run screen's "run the automation": the
    scenarios it queued, and what they came to."""
    __tablename__ = "auto_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("auto_plans.id", ondelete="SET NULL"), index=True)
    # schedule | manual
    trigger: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")
    # the test runs made to hold the results, when the plan asks for one
    run_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    started_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"))
    created_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # passed / failed / error / stopped counts once finished
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
