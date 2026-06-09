import secrets

from fastapi import Depends, Header, HTTPException

from .config import settings


async def _check_token(x_token: str | None = Header(default=None)) -> None:
    """Enforce token only when one is configured. Empty/null token = open access."""
    if not settings.token:
        return
    if x_token is None or not secrets.compare_digest(x_token, settings.token):
        raise HTTPException(status_code=401, detail="Invalid token")


async def require_user(
    x_user: str = Header(..., alias="X-User"),
    _: None = Depends(_check_token),
) -> str:
    """Require X-User on mutating requests. Also enforces token if configured."""
    return x_user


async def require_user_or_admin(
    x_user: str = Header(..., alias="X-User"),
    _: None = Depends(_check_token),
) -> tuple[str, bool]:
    return x_user, x_user in settings.admin_users
