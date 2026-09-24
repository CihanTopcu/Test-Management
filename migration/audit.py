"""Data quality audit of the migrated database.

verify.py answers "did everything arrive?". This answers "is what arrived
usable?" -- dangling references, custom-field values with no definition,
dropdown values that map to nothing, broken attachment blobs, mangled
encodings and impossible timestamps.

Findings are graded: ERROR is something that will break the application,
WARN is something a human should look at, INFO is context.
"""
import hashlib
import os
import sys
from collections import Counter

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend"))
from app.config import get_settings  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

findings = Counter()


def report(level, title, detail=""):
    findings[level] += 1
    mark = {"ERROR": "!!", "WARN": " !", "INFO": "  "}[level]
    print(f"{mark} {level:<5} {title}" + (f"  — {detail}" if detail else ""))


def ok(title, detail=""):
    print(f"   OK    {title}" + (f"  — {detail}" if detail else ""))


def main():
    url = os.environ.get("DATABASE_URL") or get_settings().database_url
    engine = create_engine(url, future=True)
    storage = get_settings().storage_dir

    with engine.connect() as c:
        def scalar(sql, **kw):
            return c.execute(text(sql), kw).scalar()

        print("=== 1. Referans bütünlüğü ===")
        checks = [
            ("suite'i olmayan case",
             "SELECT count(*) FROM cases x WHERE NOT EXISTS "
             "(SELECT 1 FROM suites s WHERE s.id = x.suite_id)", "ERROR"),
            ("section'ı olmayan case",
             "SELECT count(*) FROM cases x WHERE NOT EXISTS "
             "(SELECT 1 FROM sections s WHERE s.id = x.section_id)", "ERROR"),
            ("parent'ı kayıp section",
             "SELECT count(*) FROM sections x WHERE x.parent_id IS NOT NULL AND NOT EXISTS "
             "(SELECT 1 FROM sections p WHERE p.id = x.parent_id)", "ERROR"),
            ("run'ı olmayan test",
             "SELECT count(*) FROM tests x WHERE NOT EXISTS "
             "(SELECT 1 FROM runs r WHERE r.id = x.run_id)", "ERROR"),
            ("test'i olmayan sonuç",
             "SELECT count(*) FROM results x WHERE NOT EXISTS "
             "(SELECT 1 FROM tests t WHERE t.id = x.test_id)", "ERROR"),
            ("case'i silinmiş/kayıp test",
             "SELECT count(*) FROM tests x WHERE x.case_id IS NOT NULL AND NOT EXISTS "
             "(SELECT 1 FROM cases k WHERE k.id = x.case_id)", "WARN"),
            ("parent'ı kayıp milestone",
             "SELECT count(*) FROM milestones x WHERE x.parent_id IS NOT NULL AND NOT EXISTS "
             "(SELECT 1 FROM milestones p WHERE p.id = x.parent_id)", "ERROR"),
            ("var olmayan kullanıcıya atıf yapan case",
             "SELECT count(*) FROM cases x WHERE x.created_by IS NOT NULL AND NOT EXISTS "
             "(SELECT 1 FROM users u WHERE u.id = x.created_by)", "WARN"),
            ("var olmayan kullanıcıya atıf yapan sonuç",
             "SELECT count(*) FROM results x WHERE x.created_by IS NOT NULL AND NOT EXISTS "
             "(SELECT 1 FROM users u WHERE u.id = x.created_by)", "WARN"),
            ("tanımsız statüye atıf yapan sonuç",
             "SELECT count(*) FROM results x WHERE x.status_id IS NOT NULL AND NOT EXISTS "
             "(SELECT 1 FROM statuses s WHERE s.id = x.status_id)", "ERROR"),
            ("tanımsız tipe atıf yapan case",
             "SELECT count(*) FROM cases x WHERE x.type_id IS NOT NULL AND NOT EXISTS "
             "(SELECT 1 FROM case_types t WHERE t.id = x.type_id)", "ERROR"),
            ("case'i olmayan adım",
             "SELECT count(*) FROM case_steps x WHERE NOT EXISTS "
             "(SELECT 1 FROM cases k WHERE k.id = x.case_id)", "ERROR"),
        ]
        for label, sql, level in checks:
            n = scalar(sql)
            if n:
                report(level, label, f"{n} kayıt")
            else:
                ok(label, "0")

        print("\n=== 2. Özel alan değerleri ===")
        defined = {r[0] for r in c.execute(text(
            "SELECT system_name FROM custom_fields WHERE entity = 'case'"))}
        used = {r[0] for r in c.execute(text(
            "SELECT DISTINCT jsonb_object_keys(custom) FROM cases"))}
        unknown = sorted(used - defined)
        if unknown:
            report("WARN", "tanımı olmayan özel alan anahtarı",
                   ", ".join(unknown[:8]) + (" …" if len(unknown) > 8 else ""))
        else:
            ok("her özel alan anahtarının tanımı var", f"{len(used)} anahtar")

        unused = sorted(defined - used)
        if unused:
            report("INFO", "hiç kullanılmayan tanımlı alan",
                   f"{len(unused)} adet: " + ", ".join(unused[:6]))

        # TestRail writes 0 into a dropdown that was never set; no option list
        # here starts below 1, so 0 always means "none" rather than a value we
        # failed to import. Counted, not flagged.
        zeros = c.execute(text("""
            SELECT count(*) FROM cases k
            JOIN custom_fields f ON f.entity = 'case' AND k.custom ? f.system_name
            WHERE f.field_type = 'dropdown'
              AND trim(both '"' from (k.custom -> f.system_name)::text) = '0'
        """)).scalar()
        if zeros:
            report("INFO", "dropdown'da 'seçim yok' (0) değeri",
                   f"{zeros} case — boş kabul edilir")

        # dropdown values that resolve to nothing
        rows = c.execute(text("""
            SELECT f.system_name, f.label, count(*) FROM cases k
            JOIN custom_fields f ON f.entity = 'case'
              AND k.custom ? f.system_name
            WHERE f.field_type = 'dropdown'
              AND trim(both '"' from (k.custom -> f.system_name)::text) <> '0'
              AND NOT EXISTS (
                SELECT 1 FROM custom_field_options o
                WHERE o.field_id = f.id
                  AND o.value::text = trim(both '"' from (k.custom -> f.system_name)::text))
            GROUP BY 1, 2 ORDER BY 3 DESC
        """)).all()
        if rows:
            for name, label, n in rows[:8]:
                report("WARN", f"dropdown değeri seçenek listesinde yok: {label}",
                       f"{n} case ({name})")
        else:
            ok("tüm dropdown değerleri tanımlı seçeneklere karşılık geliyor")

        print("\n=== 3. İçerik tutarlılığı ===")
        n = scalar("SELECT count(*) FROM cases WHERE title IS NULL OR btrim(title) = ''")
        (report("ERROR", "başlığı boş case", f"{n} kayıt") if n
         else ok("başlığı boş case", "0"))

        n = scalar("SELECT count(*) FROM case_steps WHERE "
                   "(content IS NULL OR btrim(content) = '') AND "
                   "(expected IS NULL OR btrim(expected) = '')")
        (report("WARN", "tamamen boş adım satırı", f"{n} kayıt") if n
         else ok("tamamen boş adım satırı", "0"))

        n = scalar("SELECT count(*) FROM cases WHERE updated_on < created_on")
        (report("WARN", "güncelleme tarihi oluşturmadan eski", f"{n} kayıt") if n
         else ok("tarih sıralaması tutarlı"))

        n = scalar("SELECT count(*) FROM results WHERE created_on > now() + interval '1 day'")
        (report("WARN", "gelecek tarihli sonuç", f"{n} kayıt") if n
         else ok("gelecek tarihli sonuç", "0"))

        # mojibake: the classic UTF-8-read-as-latin1 signatures
        n = scalar("SELECT count(*) FROM cases WHERE title LIKE '%Ã%' "
                   "OR title LIKE '%Å%' OR title LIKE '%Ä±%'")
        (report("ERROR", "bozuk karakter kodlaması (mojibake)", f"{n} case") if n
         else ok("karakter kodlaması temiz", "Türkçe karakterler bozulmamış"))

        sample = c.execute(text(
            "SELECT title FROM cases WHERE title ~ '[çğıöşüÇĞİÖŞÜ]' LIMIT 3")).all()
        ok("Türkçe karakter örneği",
           sample[0][0][:60] if sample else "örnek bulunamadı")

        print("\n=== 4. Ekler ===")
        total = scalar("SELECT count(*) FROM attachments")
        missing_file, size_mismatch, checked = 0, 0, 0
        bad_hash = 0
        rows = c.execute(text(
            "SELECT testrail_id, storage_key, size, checksum_sha256 FROM attachments")).all()
        for att_id, key, size, checksum in rows:
            path = os.path.join(storage, key)
            if not os.path.exists(path):
                missing_file += 1
                continue
            actual = os.path.getsize(path)
            if size and actual != size:
                size_mismatch += 1
            if checked < 25 and checksum:
                with open(path, "rb") as f:
                    if hashlib.sha256(f.read()).hexdigest() != checksum:
                        bad_hash += 1
                checked += 1
        ok("kayıtlı ek", f"{total}")
        (report("ERROR", "dosyası bulunamayan ek", f"{missing_file}") if missing_file
         else ok("dosyası bulunamayan ek", "0"))
        (report("WARN", "boyutu tutmayan ek", f"{size_mismatch}") if size_mismatch
         else ok("boyutu tutmayan ek", "0"))
        (report("ERROR", "sağlama toplamı tutmayan ek", f"{bad_hash}/{checked}") if bad_hash
         else ok("sağlama toplamı doğrulandı", f"{checked} örnek"))

        # Images live in the step rows as well as the custom fields, so both
        # have to be searched -- looking only at cases.custom undercounts by
        # an order of magnitude.
        n = scalar("""
            SELECT count(DISTINCT k.id) FROM cases k
            LEFT JOIN case_steps s ON s.case_id = k.id
            WHERE k.custom::text LIKE '%attachments/get/%'
               OR s.content LIKE '%attachments/get/%'
               OR s.expected LIKE '%attachments/get/%'
        """)
        unresolved = scalar("""
            WITH refs AS (
              SELECT DISTINCT k.id AS case_id,
                     (regexp_matches(
                        coalesce(k.custom::text, '') || coalesce(s.content, '')
                          || coalesce(s.expected, ''),
                        'attachments/get/([0-9a-zA-Z-]+)', 'g'))[1] AS ref
              FROM cases k LEFT JOIN case_steps s ON s.case_id = k.id
              WHERE k.custom::text LIKE '%attachments/get/%'
                 OR s.content LIKE '%attachments/get/%'
                 OR s.expected LIKE '%attachments/get/%'
            )
            SELECT count(DISTINCT case_id) FROM refs
            WHERE NOT EXISTS (SELECT 1 FROM attachments a WHERE a.testrail_id = refs.ref)
        """)
        report("WARN", "gömülü görseli olan case",
               f"{n} case; {unresolved} tanesinde erişilemeyen görsel var")

        print("\n=== 5. Yürütme verisi ===")
        n = scalar("SELECT count(*) FROM runs WHERE suite_id IS NULL")
        (report("WARN", "suite'i olmayan koşum", f"{n}") if n
         else ok("suite'i olmayan koşum", "0"))
        n = scalar("SELECT count(*) FROM tests WHERE status_id IS NULL")
        report("INFO", "statüsü boş test", f"{n} (untested sayılır)")
        n = scalar("""SELECT count(*) FROM tests t WHERE t.status_id IS NOT NULL
                      AND NOT EXISTS (SELECT 1 FROM results r WHERE r.test_id = t.id)""")
        report("INFO", "statüsü var ama sonuç kaydı yok", f"{n}")
        # Two corrections to what counts as drift. Ties are broken by id,
        # because TestRail writes several results within the same second and
        # ordering on the timestamp alone picks an arbitrary one. And a
        # result with no status is a comment: it never moved the test.
        drift = scalar("""
            SELECT count(*) FROM tests t
            JOIN LATERAL (SELECT status_id FROM results r WHERE r.test_id = t.id
                          AND r.status_id IS NOT NULL
                          ORDER BY created_on DESC, id DESC LIMIT 1) last ON true
            WHERE t.status_id IS DISTINCT FROM last.status_id
        """)
        (report("WARN", "test statüsü son sonuçla uyuşmuyor", f"{drift}") if drift
         else ok("test statüsü son sonuçla tutarlı"))

        print("\n=== 6. Geçmiş ===")
        n = scalar("SELECT count(*) FROM case_history")
        report("INFO", "case geçmiş kaydı", f"{n}")
        if n:
            n2 = scalar("""SELECT count(*) FROM case_history h WHERE NOT EXISTS
                           (SELECT 1 FROM cases k WHERE k.id = h.case_id)""")
            (report("ERROR", "case'i olmayan geçmiş kaydı", f"{n2}") if n2
             else ok("geçmiş kayıtları geçerli case'lere bağlı"))

    print("\n" + "=" * 62)
    print(f"SONUÇ: {findings['ERROR']} hata, {findings['WARN']} uyarı, "
          f"{findings['INFO']} bilgi")
    sys.exit(1 if findings["ERROR"] else 0)


if __name__ == "__main__":
    main()
