from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Action = Literal["lock", "unlock"]


async def run(script_path: str, action: Action) -> None:
    if not script_path:
        return

    path = Path(script_path)
    if not path.exists():
        logger.warning("Access control script not found: %s", script_path)
        return

    try:
        proc = await asyncio.create_subprocess_exec(
            str(path), action,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode != 0:
            logger.error("Access control %s failed (rc=%d): %s", action, proc.returncode, stderr.decode())
        else:
            logger.info("Access control %s OK", action)
    except asyncio.TimeoutError:
        logger.error("Access control script timed out")
    except Exception:
        logger.exception("Error running access control script")
