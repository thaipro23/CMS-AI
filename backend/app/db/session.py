from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


def _engine_kwargs(database_url: str) -> dict:
    """Build SQLAlchemy engine kwargs without breaking sqlite unit tests.

    Production uses PostgreSQL. Pool sizing and statement timeout are intentionally
    configured in one place so API workers and Celery workers share the same DB
    behavior. SQLite does not accept QueuePool-only kwargs, so keep dev/test safe.
    """
    url = make_url(database_url)
    kwargs: dict = {'pool_pre_ping': True}
    if url.get_backend_name().startswith('postgresql'):
        kwargs.update(
            pool_size=max(1, int(settings.db_pool_size)),
            max_overflow=max(0, int(settings.db_max_overflow)),
            pool_timeout=max(1, int(settings.db_pool_timeout)),
            pool_recycle=max(60, int(settings.db_pool_recycle)),
        )
        timeout_ms = int(settings.db_statement_timeout_ms or 0)
        if timeout_ms > 0:
            # psycopg accepts libpq options. This is applied per connection.
            kwargs['connect_args'] = {'options': f'-c statement_timeout={timeout_ms}'}
    return kwargs


engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
