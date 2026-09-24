"""Create the database the test suite owns. Run once, with a superuser.

The application role deliberately has no CREATEDB -- an app that can create
databases has a bigger blast radius than this one needs -- so the test
database is made here, owned by that role, and the suite resets its schema on
every run instead of making a new one.

    python ops/mktestdb.py

Reads the app credentials from .env and the superuser password from
%LOCALAPPDATA%\\testmgmt-pg\\superuser_password.txt (override with
PG_SUPERUSER_PASSWORD_FILE or PG_SUPERUSER_PASSWORD).
"""
import io
import os
import sys

import psycopg

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = os.environ.get("TEST_DATABASE_NAME", "testmgmt_test")


def superuser_password() -> str:
    if os.environ.get("PG_SUPERUSER_PASSWORD"):
        return os.environ["PG_SUPERUSER_PASSWORD"]
    path = os.environ.get(
        "PG_SUPERUSER_PASSWORD_FILE",
        os.path.expandvars(r"%LOCALAPPDATA%\testmgmt-pg\superuser_password.txt"))
    with io.open(path, encoding="utf-8") as handle:
        return handle.read().strip()


def main() -> None:
    with io.open(os.path.join(ROOT, ".env"), encoding="utf-8") as handle:
        url = handle.read().split("DATABASE_URL=")[1].split("\n")[0].strip()

    # postgresql+psycopg://user:pw@host:port/db
    creds, _, hostpart = url.split("://", 1)[1].partition("@")
    app_user = creds.split(":", 1)[0]
    host, _, rest = hostpart.partition(":")
    port = rest.split("/")[0]

    admin = f"postgresql://postgres:{superuser_password()}@{host}:{port}/postgres"
    with psycopg.connect(admin, autocommit=True) as conn:
        if conn.execute("select 1 from pg_database where datname = %s",
                        (NAME,)).fetchone():
            print(f"{NAME} zaten var")
        else:
            conn.execute(f'CREATE DATABASE "{NAME}" OWNER {app_user}')
            print(f"{NAME} olusturuldu, sahibi {app_user}")

    # the role has to own the public schema too, or create_all fails on PG 15+
    target = admin.rsplit("/", 1)[0] + f"/{NAME}"
    with psycopg.connect(target, autocommit=True) as conn:
        conn.execute(f"ALTER SCHEMA public OWNER TO {app_user}")
        conn.execute(f'GRANT ALL ON DATABASE "{NAME}" TO {app_user}')
    print(f"public semasi {app_user} kullanicisina verildi")

    test_url = url.rsplit("/", 1)[0] + f"/{NAME}"
    env_test = os.path.join(ROOT, ".env.test")
    if not os.path.exists(env_test):
        with io.open(env_test, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(
                "# Yalnizca testler icin. backend/tests bu veritabaninin"
                " semasini siler.\n"
                f"TEST_DATABASE_URL={test_url}\nDATABASE_URL={test_url}\n")
        print("olusturuldu: .env.test")
    print(f"\ncd backend && python -m pytest")


if __name__ == "__main__":
    main()
