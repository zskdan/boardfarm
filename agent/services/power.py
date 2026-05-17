import asyncio
import logging
import sys
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

PowerAction = Literal["on", "off", "reset"]


async def run(
    script_path: str,
    action: PowerAction,
    extra_args: dict | None = None,
) -> bool:
    if not script_path:
        logger.warning("No power script configured")
        return False

    path = Path(script_path)
    if not path.exists():
        logger.error("Power script not found: %s", script_path)
        return False

    cmd = [sys.executable, str(path), "--action", action]
    if extra_args:
        for k, v in extra_args.items():
            cmd += [f"--{k.replace('_', '-')}", str(v)]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            logger.error(
                "Power script failed (rc=%d): %s", proc.returncode, stderr.decode()
            )
            return False
        logger.info("Power %s OK: %s", action, stdout.decode().strip())
        return True
    except asyncio.TimeoutError:
        logger.error("Power script timed out")
        return False
    except Exception:
        logger.exception("Error running power script")
        return False
