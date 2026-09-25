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
