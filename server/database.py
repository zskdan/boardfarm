from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

engine = create_async_engine(
    f"sqlite+aiosqlite:///{settings.db_path}",
    echo=False,
)

async_session: sessionmaker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

_MIGRATIONS = [
    "ALTER TABLE devices ADD COLUMN deployed_version TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE devices ADD COLUMN version_script TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE devices ADD COLUMN version_poll_interval INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE devices RENAME COLUMN access_control TO access_control_script",
    "ALTER TABLE devices ADD COLUMN redeployment_script TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE devices ADD COLUMN version_ref_file TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE agents ADD COLUMN agent_version TEXT NOT NULL DEFAULT ''",
]


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for sql in _MIGRATIONS:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass  # column already exists


async def get_db():
    async with async_session() as session:
        yield session
