import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog


async def log_action(
    db: AsyncSession,
    action: str,
    username: str = "",
    device_ref: str | None = None,
    device_name: str = "",
    detail: str = "",
    device_id: str = "",
) -> None:
    entry = AuditLog(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        action=action,
        username=username,
        device_ref=device_ref,
        device_name=device_name,
        device_id=device_id,
        detail=detail,
    )
    db.add(entry)
    # caller is responsible for committing
