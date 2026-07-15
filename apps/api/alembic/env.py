import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.core.database import Base

# Import all module models so they register on Base.metadata before autogenerate.
from app.modules.users.models import User  # noqa: F401
from app.modules.organizations.models import (  # noqa: F401
    Organization,
    OrganizationInvite,
    OrganizationMember,
)
from app.modules.auth.models import AuthToken  # noqa: F401
from app.modules.documents.models import Document, DocumentChunk, DocumentVersion  # noqa: F401
from app.modules.chat.models import ChatMessage, Conversation  # noqa: F401
from app.modules.agents.models import AgentRun  # noqa: F401
from app.modules.workflows.models import Ticket  # noqa: F401
from app.modules.audit.models import AuditLog  # noqa: F401

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
