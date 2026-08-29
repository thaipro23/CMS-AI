from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.core.config import settings
from app.db.session import Base
from app.models import course, question, cost, job, question_bank, rbac, academic  # noqa: F401

config = context.config
config.set_main_option('sqlalchemy.url', settings.database_url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _widen_alembic_version_num(connection) -> None:
    # Old deployments created alembic_version.version_num as VARCHAR(32).
    # New semantic revision IDs are longer, so guard before Alembic writes head.
    try:
        connection.exec_driver_sql(
            'ALTER TABLE IF EXISTS alembic_version '
            'ALTER COLUMN version_num TYPE VARCHAR(255)'
        )
        connection.commit()
    except Exception:
        connection.rollback()


def run_migrations_offline() -> None:
    url = config.get_main_option('sqlalchemy.url')
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix='sqlalchemy.', poolclass=pool.NullPool)
    with connectable.connect() as connection:
        _widen_alembic_version_num(connection)
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
