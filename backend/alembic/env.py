from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import settings
from app.database.base import Base

# ==========================================================
# Alembic Configuration
# ==========================================================

config = context.config

# ==========================================================
# Determine which database to use
#
# Default:
#     Development database
#
# Usage:
#     alembic upgrade head
#
# Test database:
#     alembic -x db=test upgrade head
# ==========================================================

x_args = context.get_x_argument(as_dictionary=True)

if x_args.get("db") == "test":
    database_url = settings.TEST_SYNC_DATABASE_URL
else:
    database_url = settings.SYNC_DATABASE_URL

config.set_main_option("sqlalchemy.url", database_url)

# ==========================================================
# Logging
# ==========================================================

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ==========================================================
# Metadata
# ==========================================================

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in offline mode.
    """

    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in online mode.
    """

    connectable = create_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()