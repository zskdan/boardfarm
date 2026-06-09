import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog


async def log_action(
    db: AsyncSession,
    action: str,
    username: str = "",
    board_id: str | None = None,
    board_name: str = "",
    detail: str = "",
) -> None:
    entry = AuditLog(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        action=action,
        username=username,
        board_id=board_id,
        board_name=board_name,
        detail=detail,
    )
    db.add(entry)
    # caller is responsible for committing
