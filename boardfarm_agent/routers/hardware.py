import asyncio
import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_agent_auth
from ..config import config
from ..services import access_control, hw_server, power
from ..services import version as version_svc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["hardware"])


def _get_device(device_id: str):
    for b in config.devices:
        if b.id == device_id:
            return b
    raise HTTPException(status_code=404, detail="Device not managed by this agent")


@router.post("/devices/{device_id}/services/start")
async def start_services(device_id: str, _: None = Depends(require_agent_auth)):
    device = _get_device(device_id)
    jtag_ok = await hw_server.start(device_id, device.jtag_port)
    await access_control.run(device.access_control_script, "unlock")
    return {"jtag_started": jtag_ok}


@router.post("/devices/{device_id}/services/stop")
async def stop_services(device_id: str, _: None = Depends(require_agent_auth)):
    device = _get_device(device_id)
    await hw_server.stop(device_id)
    await access_control.run(device.access_control_script, "lock")
    return {"stopped": True}


class PowerBody(BaseModel):
    action: Literal["on", "off", "reset"]


@router.post("/devices/{device_id}/power")
async def power_action(device_id: str, body: PowerBody, _: None = Depends(require_agent_auth)):
    device = _get_device(device_id)
    ok = await power.run(device.power_script, body.action, device.power_args)
    if not ok:
        raise HTTPException(status_code=500, detail="Power action failed")
    return {"action": body.action, "ok": True}


@router.get("/devices/{device_id}/redeploy-info")
async def redeploy_info(device_id: str, _: None = Depends(require_agent_auth)):
    device = _get_device(device_id)
    if not device.redeployment_script:
        raise HTTPException(status_code=422, detail="No redeployment script configured")
    path = Path(device.redeployment_script)
    if not path.exists():
        return {"exists": False, "script_lines": 0}
    lines = sum(1 for line in path.read_text(errors="replace").splitlines() if line.strip())
    return {"exists": True, "script_lines": max(lines, 1)}


@router.post("/devices/{device_id}/redeploy")
async def redeploy(device_id: str, _: None = Depends(require_agent_auth)):
    device = _get_device(device_id)
    if not device.redeployment_script:
        raise HTTPException(status_code=422, detail="No redeployment script configured")
    path = Path(device.redeployment_script)
    if not path.exists():
        raise HTTPException(status_code=422, detail=f"Redeployment script not found: {device.redeployment_script}")
    try:
        proc = await asyncio.create_subprocess_exec(
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        ok = proc.returncode == 0
        if not ok:
            logger.error("Redeployment script failed (rc=%d): %s", proc.returncode, stderr.decode().strip())
        else:
            logger.info("Redeployment OK for device %s", device_id)
        result = {
            "ok": ok,
            "stdout": stdout.decode().strip(),
            "stderr": stderr.decode().strip(),
            "returncode": proc.returncode,
        }
        if ok and device.version_script and config.server_url:
            new_version = await version_svc.run_script(device.version_script, device.version_ref_file or "")
            if new_version is not None:
                await version_svc.push_version(config.server_url, config.server_token, device_id, new_version)
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Redeployment script timed out (5 min)")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
