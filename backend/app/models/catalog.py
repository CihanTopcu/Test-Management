"""Configurable vocabularies: case types, priorities, statuses, templates and
the custom-field registry.

These are data, not code. TestRail lets an admin add a dropdown value or a
whole new field without a deploy, and the DGPays instance leans on that hard
(26 custom case fields, 12 custom result fields). Keeping them as rows is what
makes a 1:1 migration possible.
"""
from sqlalchemy import (Boolean, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, LegacyIdMixin, TimestampMixin


class CaseType(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "case_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class Priority(Base, LegacyIdMixin, TimestampMixin):
    __tablename__ = "priorities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(30))
    priority_level: Mapped[int] = mapped_column(Integer, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class Status(Base, LegacyIdMixin, TimestampMixin):
    """Result statuses: passed/blocked/untested/retest/failed plus customs."""
    __tablename__ = "statuses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str | None] = mapped_column(String(20))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_untested: Mapped[bool] = mapped_column(Boolean, default=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=True)


class Template(Base, LegacyIdMixin, TimestampMixin):
    """Which field layout a case uses (Text, Steps, Exploratory, BDD...)."""
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class CustomField(Base, LegacyIdMixin, TimestampMixin):
    """Definition of one custom field on a case or a result."""
    __tablename__ = "custom_fields"
    __table_args__ = (UniqueConstraint("entity", "system_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity: Mapped[str] = mapped_column(String(20), nullable=False)  # case | result
    system_name: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # string, integer, text, url, checkbox, dropdown, user, date, milestone,
    # steps, step_results, multiselect, bdd, rating
    field_type: Mapped[str] = mapped_column(String(30), nullable=False)
    is_global: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    # per-project overrides: required flag, dropdown options, template scope
    configs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class CustomFieldOption(Base):
    """Dropdown / multiselect choices, kept relational so values can be
    renamed without rewriting every case that points at them."""
    __tablename__ = "custom_field_options"
    __table_args__ = (UniqueConstraint("field_id", "value"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(
        ForeignKey("custom_fields.id", ondelete="CASCADE"), index=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
