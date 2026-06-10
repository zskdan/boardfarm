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
        # Rename tables before create_all so SQLAlchemy sees the correct names
        for rename_sql in (
            "ALTER TABLE boards RENAME TO devices",
            "ALTER TABLE setup_boards RENAME TO setup_devices",
        ):
            try:
                await conn.execute(text(rename_sql))
            except Exception:
                pass

        await conn.run_sync(Base.metadata.create_all)

        # Add columns that may be missing in older databases
        for col_def in (
            "ALTER TABLE devices ADD COLUMN device_id TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE devices ADD COLUMN serial_number TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE devices ADD COLUMN revision TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE devices ADD COLUMN device_ip TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE devices ADD COLUMN usb_device TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE devices ADD COLUMN uart_device TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE devices ADD COLUMN sdmux_control TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE devices ADD COLUMN sdmux_sdcard TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE devices ADD COLUMN access_control TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE audit_log ADD COLUMN device_id TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE bookings ADD COLUMN setup_id TEXT",
            "ALTER TABLE bookings ADD COLUMN setup_name TEXT NOT NULL DEFAULT ''",
        ):
            try:
                await conn.execute(text(col_def))
            except Exception:
                pass

        try:
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_device_id ON devices (device_id) WHERE device_id != ''"
            ))
        except Exception:
            pass

        # Rename legacy columns — silently no-ops if already renamed
        for col_rename in (
            "ALTER TABLE bookings RENAME COLUMN board_id TO device_id",
            "ALTER TABLE tools RENAME COLUMN board_id TO device_id",
            "ALTER TABLE setup_devices RENAME COLUMN board_id TO device_id",
            "ALTER TABLE audit_log RENAME COLUMN board_id TO device_ref",
            "ALTER TABLE audit_log RENAME COLUMN board_name TO device_name",
        ):
            try:
                await conn.execute(text(col_rename))
            except Exception:
                pass


async def get_db():
    async with async_session() as session:
        yield session
