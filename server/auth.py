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


async def optional_auth(
    x_token: str | None = Header(default=None),
    x_user: str | None = Header(default=None, alias="X-User"),
) -> str | None:
    if x_token is None:
        return None
    if not secrets.compare_digest(x_token, settings.token):
        raise HTTPException(status_code=401, detail="Invalid token")
    return x_user
