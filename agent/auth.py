import secrets
from fastapi import Header, HTTPException
from .config import config

async def require_agent_auth(x_agent_token: str = Header(default="")) -> None:
    """Validates calls coming FROM the server TO this agent."""
    if config.agent_token and not secrets.compare_digest(x_agent_token, config.agent_token):
        raise HTTPException(status_code=401, detail="Invalid agent token")
