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


class BoardIn(BaseModel):
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
    uart_tcp_port: int = 0
    ssh_user: str = "root"
    ssh_port: int = 0
    power_script: str = ""
    power_args: dict = {}
    enabled: bool = True


class BoardUpdate(BaseModel):
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
    uart_tcp_port: int | None = None
    ssh_user: str | None = None
    ssh_port: int | None = None
    power_script: str | None = None
    power_args: dict | None = None
    enabled: bool | None = None


class BookingOut(BaseModel):
    id: str
    board_id: str
    board_name: str = ""
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


class BoardOut(BaseModel):
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
    uart_tcp_port: int
    ssh_user: str
    ssh_port: int
    power_script: str
    power_args: dict
    enabled: bool
    agent_online: bool = False
    active_booking: BookingOut | None = None

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


class SetupBoardOut(BaseModel):
    board_id: str
    board_name: str
    device_id: str
    location: str
    agent_online: bool
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
    boards: list[SetupBoardOut]
    all_available: bool
    active_booking: SetupBookingOut | None = None

    @field_serializer("created_at")
    def _ca(self, v: datetime) -> str:
        return v.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


class SetupIn(BaseModel):
    name: str
    description: str = ""
    board_ids: list[str]


class SetupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    board_ids: list[str] | None = None


class BookSetupIn(BaseModel):
    duration_hours: int = 4
    comment: str = ""


class AuditLogOut(BaseModel):
    id: str
    timestamp: datetime
    action: str
    username: str
    board_id: str | None
    board_name: str
    device_id: str = ""
    detail: str

    @field_serializer("timestamp")
    def _ts(self, v: datetime) -> str:
        return v.strftime("%Y-%m-%dT%H:%M:%S") + "Z"

    model_config = {"from_attributes": True}
