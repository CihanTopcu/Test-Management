"""Measure the queries the application actually runs.

The archived import multiplies the execution tables by roughly ten, and the
queries that are comfortable against 88k tests are not automatically
comfortable against 800k. This times the real statements and prints the plan
for any that turn out to be sequential scans.
"""
import os
import sys
import time

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend"))
from app.config import get_settings  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

# statement, label, and the plan fragment that would mean trouble
QUERIES = [
    ("proje istatistikleri – case sayımı", """
        SELECT count(*) FROM cases c
        JOIN suites s ON s.id = c.suite_id
        WHERE s.project_id = 3 AND c.is_deleted = false
    """),
    ("proje istatistikleri – statü dağılımı", """
        SELECT t.status_id, count(*) FROM tests t
        JOIN runs r ON r.id = t.run_id
        WHERE r.project_id = 3 GROUP BY t.status_id
    """),
    ("koşum listesi (aktif)", """
        SELECT * FROM runs
        WHERE project_id = 3 AND is_archived = false
        ORDER BY created_on DESC NULLS LAST LIMIT 300
    """),
    ("koşum listesi (arşiv)", """
        SELECT * FROM runs
        WHERE project_id = 3 AND is_archived = true
        ORDER BY created_on DESC NULLS LAST LIMIT 300
    """),
    ("koşum listesi ilerlemesi", """
        SELECT t.run_id, t.status_id, count(*) FROM tests t
        WHERE t.run_id IN (SELECT id FROM runs WHERE project_id = 3 LIMIT 300)
        GROUP BY t.run_id, t.status_id
    """),
    ("koşum özeti", """
        SELECT status_id, count(*) FROM tests WHERE run_id = 73150
        GROUP BY status_id
    """),
    ("case listesi (bölüm + sıralama)", """
        SELECT * FROM cases
        WHERE suite_id = 42 AND is_deleted = false
        ORDER BY section_id, display_order LIMIT 250
    """),
    ("case araması (başlık)", """
        SELECT count(*) FROM cases
        WHERE suite_id = 42 AND is_deleted = false AND title ILIKE '%kart%'
    """),
    ("global arama", """
        SELECT * FROM cases
        WHERE is_deleted = false AND (title ILIKE '%login%' OR refs ILIKE '%login%')
        ORDER BY updated_on DESC NULLS LAST LIMIT 40
    """),
    ("özel alan filtresi", """
        SELECT count(*) FROM cases
        WHERE suite_id = 42 AND custom->>'custom_automation_type' = '2'
    """),
    ("son aktivite", """
        SELECT r.id, t.title, res.created_on FROM results res
        JOIN tests t ON t.id = res.test_id
        JOIN runs r ON r.id = t.run_id
        WHERE r.project_id = 3
        ORDER BY res.created_on DESC LIMIT 20
    """),
    ("bir testin sonuçları", """
        SELECT * FROM results WHERE test_id = 9236740
        ORDER BY created_on DESC
    """),
    ("rapor – günlük sonuç", """
        SELECT date(res.created_on), res.status_id, count(*) FROM results res
        JOIN tests t ON t.id = res.test_id
        JOIN runs r ON r.id = t.run_id
        WHERE r.project_id = 3 AND res.created_on >= now() - interval '120 days'
        GROUP BY 1, 2 ORDER BY 1
    """),
    ("rapor – hata kayıtları", """
        SELECT res.defects, count(*) FROM results res
        JOIN tests t ON t.id = res.test_id
        JOIN runs r ON r.id = t.run_id
        WHERE r.project_id = 3 AND res.defects IS NOT NULL AND res.defects <> ''
        GROUP BY 1
    """),
    ("case geçmişi", """
        SELECT * FROM case_history WHERE case_id = 15477
        ORDER BY created_on DESC
    """),
    ("bölüm ağacı", """
        SELECT * FROM sections WHERE suite_id = 42 ORDER BY display_order
    """),
]

SLOW_MS = 400


def main():
    url = os.environ.get("DATABASE_URL") or get_settings().database_url
    engine = create_engine(url, future=True)

    with engine.connect() as c:
        print("satır sayıları:")
        for table in ("cases", "tests", "results", "runs", "case_history"):
            n = c.execute(text(f"select count(*) from {table}")).scalar()
            print(f"  {table:<14} {n:>12,}".replace(",", "."))
        print()

        print(f"{'sorgu':<38} {'süre':>9}   durum")
        print("-" * 70)
        slow = []
        for label, sql in QUERIES:
            c.execute(text(sql)).fetchall()          # warm
            t0 = time.perf_counter()
            c.execute(text(sql)).fetchall()
            ms = (time.perf_counter() - t0) * 1000
            flag = "YAVAŞ" if ms > SLOW_MS else "ok"
            if ms > SLOW_MS:
                slow.append((label, sql, ms))
            print(f"{label:<38} {ms:>7.1f}ms   {flag}")

        if slow:
            print("\n" + "=" * 70)
            print("YAVAŞ SORGULARIN PLANI")
            print("=" * 70)
            for label, sql, ms in slow:
                print(f"\n--- {label} ({ms:.0f}ms) ---")
                for row in c.execute(text("EXPLAIN (ANALYZE, BUFFERS) " + sql)):
                    line = row[0]
                    mark = " <<<" if "Seq Scan" in line else ""
                    print("   " + line + mark)
        else:
            print(f"\nhepsi {SLOW_MS}ms altında")


if __name__ == "__main__":
    main()
