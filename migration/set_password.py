"""Give an imported user a password.

TestRail never exposes password hashes through its API, so every migrated
account arrives without one and cannot sign in until this is run (or until
SSO is wired up).

Usage: python migration/set_password.py <email> [password]
"""
import os
import secrets
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend"))
from app.config import get_settings  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.models import User  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    email = sys.argv[1]
    password = sys.argv[2] if len(sys.argv) > 2 else secrets.token_urlsafe(12)

    url = os.environ.get("DATABASE_URL") or get_settings().database_url
    engine = create_engine(url, future=True)
    with Session(engine) as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"kullanici bulunamadi: {email}")
            sys.exit(1)
        user.password_hash = hash_password(password)
        session.commit()
        print(f"parola ayarlandi: {user.name} <{user.email}>")
        if len(sys.argv) < 3:
            print(f"uretilen parola: {password}")


if __name__ == "__main__":
    main()
