from logging.config import fileConfig
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from alembic import context
from sqlalchemy import engine_from_config, pool
from devpilot.config import AppSettings
from devpilot.core.database import Base
from devpilot.models import governance  # noqa: F401
from devpilot.models import user  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", AppSettings().database_url)
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
