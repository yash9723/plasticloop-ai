"""Create the database named in DATABASE_URL if it does not exist (for hosts that give one server, e.g. Render).

    python -m app.scripts.ensure_database
"""
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings


def main() -> None:
    target = make_url(settings.database_url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": target.database})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()
    print(f"database {target.database}: {'exists' if exists else 'created'}")


if __name__ == "__main__":
    main()
