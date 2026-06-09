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


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migrate existing databases — ignore errors if already applied
        try:
            await conn.execute(text("ALTER TABLE boards ADD COLUMN device_id TEXT NOT NULL DEFAULT ''"))
        except Exception:
            pass
        try:
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_device_id ON boards (device_id) WHERE device_id != ''"
            ))
        except Exception:
            pass


async def get_db():
    async with async_session() as session:
        yield session
