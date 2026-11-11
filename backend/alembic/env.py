from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings

config = context.config
target_metadata = None


def run_migrations_online() -> None:
    # Sync engine on purpose: migrations run once at release time. Use the direct (non-pooled) URL if provided.
    engine = create_engine(settings.migration_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
