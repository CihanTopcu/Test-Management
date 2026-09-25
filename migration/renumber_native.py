"""Move rows created in this application out of TestRail's id range.

Until NATIVE_ID_BASE existed, every sequence stood just past the highest
imported id, so a result entered here took the very id TestRail would give
its next result -- and the cut-over sync, which writes by id, would then
overwrite it. This moves such rows (testrail_id IS NULL, id below the base)
to fresh ids from the native range, carrying every reference along.

    python migration/renumber_native.py            # what would move
    python migration/renumber_native.py --apply    # move it, in one transaction

Safe to run again: once nothing is left below the base it does nothing.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from sqlalchemy import create_engine, text  # noqa: E402

from app.bootstrap import NATIVE_ID_BASE, ensure_native_id_range  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

# Vocabularies whose ids the code names as constants (PASSED = 1, ...);
# on a fresh instance they are seeded with fixed ids and must stay put.
FIXED = {"statuses", "priorities", "case_types", "templates"}

# References that are not foreign keys: an attachment names its owner by
# type and id.
POLYMORPHIC = {"results": "result", "cases": "case", "runs": "run",
               "tests": "test", "plans": "plan", "milestones": "milestone"}


def children(conn, table: str) -> list[tuple[str, str]]:
    """Every (table, column) with a foreign key to this table."""
    return [(r[0], r[1]) for r in conn.execute(text("""
        SELECT k.conrelid::regclass::text, a.attname
        FROM pg_constraint k
        JOIN pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = ANY(k.conkey)
        WHERE k.contype = 'f' AND k.confrelid = CAST(:t AS regclass)"""), {"t": table})]


def extra_unique(conn, table: str) -> bool:
    """A unique constraint besides the key would make the copy collide."""
    return bool(conn.execute(text("""
        SELECT 1 FROM pg_constraint
        WHERE conrelid = CAST(:t AS regclass) AND contype = 'u' LIMIT 1"""),
        {"t": table}).first())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="tasi (varsayilan: yalnizca goster)")
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL") or get_settings().database_url
    engine = create_engine(url, future=True)
    ensure_native_id_range()   # new ids must come from the native range

    plan = []
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name in FIXED or "testrail_id" not in table.c:
                continue
            pk = list(table.primary_key.columns)
            if len(pk) != 1 or not pk[0].autoincrement:
                continue
            ids = [r[0] for r in conn.execute(text(
                f"SELECT {pk[0].name} FROM {table.name} "
                f"WHERE testrail_id IS NULL AND {pk[0].name} < :base ORDER BY 1"),
                {"base": NATIVE_ID_BASE})]
            if ids:
                plan.append((table, pk[0].name, ids))

        if not plan:
            print("TestRail araliginda yerel satir yok; yapilacak bir sey yok.")
            return 0
        for table, _, ids in plan:
            refs = children(conn, table.name)
            print(f"{table.name}: {len(ids)} satir {ids[:10]}{' ...' if len(ids) > 10 else ''}")
            print(f"   baglantilar: {refs or '-'}"
                  + (f", ekler ({POLYMORPHIC[table.name]})" if table.name in POLYMORPHIC else ""))
            if extra_unique(conn, table.name):
                print("   DURDU: tabloda ek bir benzersizlik kisiti var; elle ele alinmali.")
                return 1

    if not args.apply:
        print("\nHicbir sey degismedi. Tasimak icin --apply ile calistirin.")
        return 0

    moved = 0
    with engine.begin() as conn:            # all or nothing
        for table, col, ids in plan:
            seq = conn.execute(text(
                f"SELECT pg_get_serial_sequence('{table.name}', '{col}')")).scalar()
            others = [c.name for c in table.columns if c.name != col]
            cols = ", ".join([col] + others)
            refs = children(conn, table.name)
            for old in ids:
                new = conn.execute(text(f"SELECT nextval('{seq}')")).scalar()
                # copy, repoint, drop: updating the key in place would break
                # the foreign keys halfway through
                conn.execute(text(
                    f"INSERT INTO {table.name} ({cols}) "
                    f"SELECT :new, {', '.join(others)} FROM {table.name} WHERE {col} = :old"),
                    {"new": new, "old": old})
                for child, child_col in refs:
                    conn.execute(text(
                        f"UPDATE {child} SET {child_col} = :new WHERE {child_col} = :old"),
                        {"new": new, "old": old})
                if table.name in POLYMORPHIC:
                    conn.execute(text(
                        "UPDATE attachments SET entity_id = :new "
                        "WHERE entity_type = :kind AND entity_id = :old"),
                        {"new": new, "old": old, "kind": POLYMORPHIC[table.name]})
                conn.execute(text(f"DELETE FROM {table.name} WHERE {col} = :old"), {"old": old})
                print(f"{table.name} {old} -> {new}")
                moved += 1
    print(f"\n{moved} satir tasindi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
