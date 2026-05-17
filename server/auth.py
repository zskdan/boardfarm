import secrets

from fastapi import Header, HTTPException

from .config import settings


async def require_auth(
    x_token: str = Header(...),
    x_user: str = Header(..., alias="X-User"),
) -> str:
    if not secrets.compare_digest(x_token, settings.token):
        raise HTTPException(status_code=401, detail="Invalid token")
    return x_user


async def require_auth_or_admin(
    x_token: str = Header(...),
    x_user: str = Header(..., alias="X-User"),
) -> tuple[str, bool]:
    if not secrets.compare_digest(x_token, settings.token):
        raise HTTPException(status_code=401, detail="Invalid token")
    is_admin = x_user in settings.admin_users
    return x_user, is_admin


async def optional_auth(
    x_token: str | None = Header(default=None),
    x_user: str | None = Header(default=None, alias="X-User"),
) -> str | None:
    if x_token is None:
        return None
    if not secrets.compare_digest(x_token, settings.token):
        raise HTTPException(status_code=401, detail="Invalid token")
    return x_user
