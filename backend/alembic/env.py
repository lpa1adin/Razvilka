from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.core.config import settings
from app.models import Base

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

engine = create_engine(settings.database_url)

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
