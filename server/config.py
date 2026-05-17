import os
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    port: int = 8765
    token: str = "changeme"
    db_path: str = "./boardfarm.db"
    admin_users: list[str] = []

    model_config = {"env_prefix": "BOARDFARM_"}

    def model_post_init(self, __context) -> None:
        cfg_file = Path("config.yaml")
        if cfg_file.exists():
            data = yaml.safe_load(cfg_file.read_text()) or {}
            srv = data.get("server", {})
            if "port" in srv and os.getenv("BOARDFARM_PORT") is None:
                object.__setattr__(self, "port", srv["port"])
            if "token" in srv and os.getenv("BOARDFARM_TOKEN") is None:
                object.__setattr__(self, "token", srv["token"])
            if "db_path" in srv and os.getenv("BOARDFARM_DB_PATH") is None:
                object.__setattr__(self, "db_path", srv["db_path"])
            if "admin_users" in srv and os.getenv("BOARDFARM_ADMIN_USERS") is None:
                object.__setattr__(self, "admin_users", srv["admin_users"])


settings = Settings()
