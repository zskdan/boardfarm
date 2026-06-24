import json
from datetime import datetime, timezone

from pydantic import BaseModel, field_serializer, field_validator, model_validator


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AgentOut(BaseModel):
    id: str
    name: str
    url: str
    last_seen: datetime
    online: bool = False

    @model_validator(mode="after")
    def compute_online(self) -> "AgentOut":
        delta = (_now_utc() - self.last_seen).total_seconds()
        self.online = delta < 90
        return self

    @field_serializer("last_seen")
    def _dt(self, v: datetime) -> str:
        return v.strftime("%Y-%m-%dT%H:%M:%S") + "Z"

    model_config = {"from_attributes": True}


class DeviceIn(BaseModel):
    name: str
    serial_number: str = ""
    revision: str = ""
    description: str = ""
    location: str = ""
    current_notes: str = ""
    device_ip: str = ""
    host_ip: str | None = None
    features: dict = {}
    jtag_port: int = 0
    ssh_user: str = "root"
    ssh_port: int = 0
    power_script: str = ""
    power_args: dict = {}
    usb_device: str = ""
    uart_device: str = ""
    sdmux_control: str = ""
    sdmux_sdcard: str = ""
    access_control_script: str = ""
    enabled: bool = True
    version_script: str = ""
    version_ref_file: str = ""
    version_poll_interval: int = 0
    redeployment_script: str = ""


class DeviceUpdate(BaseModel):
    name: str | None = None
    serial_number: str | None = None
    revision: str | None = None
    description: str | None = None
    location: str | None = None
    current_notes: str | None = None
    device_ip: str | None = None
    host_ip: str | None = None
    features: dict | None = None
    jtag_port: int | None = None
    ssh_user: str | None = None
    ssh_port: int | None = None
    power_script: str | None = None
    power_args: dict | None = None
    usb_device: str | None = None
    uart_device: str | None = None
    sdmux_control: str | None = None
    sdmux_sdcard: str | None = None
    access_control_script: str | None = None
    enabled: bool | None = None
    version_script: str | None = None
    version_ref_file: str | None = None
    version_poll_interval: int | None = None
    redeployment_script: str | None = None


class BookingOut(BaseModel):
    id: str
    device_id: str
    device_name: str = ""
    username: str
    start_time: datetime
    end_time: datetime
    extended: bool
    active: bool
    release_reason: str
    comment: str = ""
    setup_id: str | None = None
    setup_name: str = ""

    @field_serializer("start_time")
    def _start_time(self, v: datetime) -> str:
        return v.strftime("%Y-%m-%dT%H:%M:%S") + "Z"

    @field_serializer("end_time")
    def _end_time(self, v: datetime) -> str:
        return v.strftime("%Y-%m-%dT%H:%M:%S") + "Z"

    model_config = {"from_attributes": True}


class ToolIn(BaseModel):
    type: str
    model: str = ""
    connection: str = "usb"
    connection_detail: str = ""
    notes: str = ""


class ToolOut(BaseModel):
    id: str
    device_id: str
    type: str
    model: str
    connection: str
    connection_detail: str
    notes: str

    model_config = {"from_attributes": True}


class DeviceOut(BaseModel):
    id: str
    device_id: str = ""
    serial_number: str = ""
    revision: str = ""
    name: str
    description: str
    location: str
    current_notes: str = ""
    device_ip: str = ""
    agent_id: str | None
    host_ip: str | None
    features: dict
    jtag_port: int
    ssh_user: str
    ssh_port: int
    power_script: str
    power_args: dict
    usb_device: str = ""
    uart_device: str = ""
    sdmux_control: str = ""
    sdmux_sdcard: str = ""
    access_control_script: str = ""
    enabled: bool
    agent_online: bool = False
    deployed_version: str = ""
    version_script: str = ""
    version_ref_file: str = ""
    version_poll_interval: int = 0
    redeployment_script: str = ""
    active_booking: BookingOut | None = None
    tools: list[ToolOut] = []

    @field_validator("features", "power_args", mode="before")
    @classmethod
    def parse_json_str(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    model_config = {"from_attributes": True}


class CommandsOut(BaseModel):
    jtag_connect: str
    vivado_tcl: str
    uart: str
    ssh: str
    power_on: str


class SetupDeviceOut(BaseModel):
    id: str
    name: str
    device_id: str
    location: str
    agent_online: bool
    deployed_version: str = ""
    version_script: str = ""
    active_booking_username: str | None = None
    active_booking_setup_name: str | None = None


class SetupBookingOut(BaseModel):
    username: str
    start_time: datetime
    end_time: datetime

    @field_serializer("start_time")
    def _st(self, v: datetime) -> str:
        return v.strftime("%Y-%m-%dT%H:%M:%S") + "Z"

    @field_serializer("end_time")
    def _et(self, v: datetime) -> str:
        return v.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


class SetupOut(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime
    devices: list[SetupDeviceOut]
    all_available: bool
    active_booking: SetupBookingOut | None = None

    @field_serializer("created_at")
    def _ca(self, v: datetime) -> str:
        return v.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


class SetupIn(BaseModel):
    name: str
    description: str = ""
    device_ids: list[str]


class SetupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    device_ids: list[str] | None = None


class BookSetupIn(BaseModel):
    duration_hours: int = 4
    comment: str = ""


class AuditLogOut(BaseModel):
    id: str
    timestamp: datetime
    action: str
    username: str
    device_ref: str | None
    device_name: str
    device_id: str = ""
    detail: str

    @field_serializer("timestamp")
    def _ts(self, v: datetime) -> str:
        return v.strftime("%Y-%m-%dT%H:%M:%S") + "Z"

    model_config = {"from_attributes": True}
