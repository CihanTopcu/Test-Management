"""First-run setup.

A fresh on-prem install has an empty database and nobody who can sign in.
Rather than make somebody run psql before they can open the page, the app
creates its schema and, if there are no users at all, one administrator from
the environment.

This only ever fires on an empty instance: the moment a single user row
exists it does nothing, so it cannot overwrite a real account or resurrect a
deleted one.
"""
import logging
import secrets

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .config import get_settings
from .db import engine
from .models import (Base, CaseType, Priority, Role, Status, Template,
                     User)
from .security import hash_password

log = logging.getLogger("bootstrap")

DEFAULT_ROLES = [
    ("Admin", ["read", "write_cases", "write_runs", "write_results",
               "manage_project", "admin"]),
    ("Lead", ["read", "write_cases", "write_runs", "write_results",
              "manage_project"]),
    ("Tester", ["read", "write_runs", "write_results"]),
    ("Designer", ["read", "write_cases"]),
    ("Read-only", ["read"]),
]


# The ids are TestRail's, deliberately: an instance seeded here and later
# fed a TestRail migration must line up rather than collide, and every
# imported result already refers to status 1 for passed and 5 for failed.
DEFAULT_STATUSES = [
    # id, name, label, colour, untested?, final?
    (1, "passed", "Passed", "#16a34a", False, True),
    (2, "blocked", "Blocked", "#64748b", False, True),
    (3, "untested", "Untested", "#cbd5e1", True, False),
    (4, "retest", "Retest", "#f59e0b", False, False),
    (5, "failed", "Failed", "#e11d48", False, True),
]

DEFAULT_CASE_TYPES = [
    (1, "Automated", False), (2, "Functionality", False),
    (3, "Performance", False), (4, "Regression", False),
    (5, "Usability", False), (6, "Other", True),
    (7, "Accessibility", False), (8, "Compatibility", False),
    (9, "Destructive", False), (10, "Security", False),
    (11, "Smoke & Sanity", False),
]

DEFAULT_PRIORITIES = [
    (1, "Low", "Low", 1, False), (2, "Medium", "Medium", 2, True),
    (3, "High", "High", 3, False), (4, "Critical", "Critical", 4, False),
]

DEFAULT_TEMPLATES = [
    (1, "Test Case (Text)", True),
    (2, "Test Case (Steps)", False),
    (3, "Exploratory Session", False),
]


def seed_vocabularies(session: Session) -> None:
    """Create the lookup rows, each only if that table is empty.

    Checked per table rather than all at once, so an instance that already
    carries migrated statuses still gets templates if it somehow lacks them.
    """
    if not session.scalar(select(func.count()).select_from(Status)):
        for sid, name, label, color, untested, final in DEFAULT_STATUSES:
            session.add(Status(id=sid, name=name, label=label, color=color,
                               is_system=True, is_untested=untested,
                               is_final=final))
        log.warning("varsayilan durumlar olusturuldu")

    if not session.scalar(select(func.count()).select_from(CaseType)):
        for cid, name, default in DEFAULT_CASE_TYPES:
            session.add(CaseType(id=cid, name=name, is_default=default))
        log.warning("varsayilan case tipleri olusturuldu")

    if not session.scalar(select(func.count()).select_from(Priority)):
        for pid, name, short, level, default in DEFAULT_PRIORITIES:
            session.add(Priority(id=pid, name=name, short_name=short,
                                 priority_level=level, is_default=default))
        log.warning("varsayilan oncelikler olusturuldu")

    if not session.scalar(select(func.count()).select_from(Template)):
        for tid, name, default in DEFAULT_TEMPLATES:
            session.add(Template(id=tid, name=name, is_default=default))
        log.warning("varsayilan sablonlar olusturuldu")

    session.commit()


# Trigram indexes cannot be expressed as SQLAlchemy Index objects without the
# extension being present first, and they are what makes the search box usable:
# the global search drops from 94ms to under 2ms with them.
TRIGRAM_INDEXES = [
    ("ix_cases_title_trgm", "cases", "title"),
    ("ix_cases_refs_trgm", "cases", "refs"),
    ("ix_runs_name_trgm", "runs", "name"),
]


def ensure_search_indexes() -> None:
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        try:
            c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        except Exception as exc:
            # a locked-down database may not allow extensions; search still
            # works, just linearly
            log.warning("pg_trgm kurulamadi, arama indekssiz calisacak: %s",
                        str(exc)[:120])
            return
        for name, table, column in TRIGRAM_INDEXES:
            c.execute(text(
                f"CREATE INDEX IF NOT EXISTS {name} ON {table} "
                f"USING gin ({column} gin_trgm_ops)"))


# Columns added after the first deployment. create_all() only creates
# missing tables, so an existing database needs these spelled out.
LATE_COLUMNS = [
    ("sections", "is_deleted", "boolean NOT NULL DEFAULT false"),
    ("projects", "default_role_id", "integer REFERENCES roles(id)"),
]


def ensure_late_columns() -> None:
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        for table, column, spec in LATE_COLUMNS:
            c.execute(text(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {spec}"))


def ensure_no_access_role(session: Session) -> None:
    """The role that closes a project, present on every instance.

    A migrated instance brings TestRail's own; a fresh one never had it, so
    there was no way to make a project private at all.
    """
    if not session.scalar(
            select(Role).where(func.lower(Role.name) == "no access")):
        session.add(Role(name="No Access", permissions={"capabilities": []}))
        session.commit()


def run() -> None:
    settings = get_settings()
    Base.metadata.create_all(engine)
    ensure_late_columns()
    ensure_search_indexes()

    with Session(engine) as session:
        # unconditional: these are the rows every write path depends on, and
        # an instance can have users while an upgrade adds a new lookup table
        seed_vocabularies(session)
        ensure_no_access_role(session)

        if session.scalar(select(func.count()).select_from(User)):
            return  # an instance with users is not a fresh one

        log.warning("bos veritabani: baslangic kurulumu yapiliyor")
        for name, capabilities in DEFAULT_ROLES:
            if not session.scalar(select(Role).where(Role.name == name)):
                session.add(Role(name=name,
                                 permissions={"capabilities": capabilities}))
        session.flush()

        admin_role = session.scalar(select(Role).where(Role.name == "Admin"))
        password = settings.bootstrap_password or secrets.token_urlsafe(12)
        session.add(User(
            name="Yönetici", email=settings.bootstrap_email,
            role_id=admin_role.id if admin_role else None,
            is_active=True, password_hash=hash_password(password),
        ))
        session.commit()

        log.warning("yonetici hesabi olusturuldu: %s", settings.bootstrap_email)
        if not settings.bootstrap_password:
            # printed once, to the container log, because otherwise nobody can
            # get in; set BOOTSTRAP_PASSWORD to choose it yourself
            log.warning("gecici parola: %s  — ilk giristen sonra degistirin",
                        password)
