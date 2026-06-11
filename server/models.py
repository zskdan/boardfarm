from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Setup(Base):
    __tablename__ = "setups"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    setup_devices: Mapped[list["SetupDevice"]] = relationship("SetupDevice", back_populates="setup", cascade="all, delete-orphan")


class SetupDevice(Base):
    __tablename__ = "setup_devices"

    setup_id: Mapped[str] = mapped_column(String, ForeignKey("setups.id", ondelete="CASCADE"), primary_key=True)
    device_id: Mapped[str] = mapped_column(String, ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True)
    setup: Mapped["Setup"] = relationship("Setup", back_populates="setup_devices")
    device: Mapped["Device"] = relationship("Device")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[str] = mapped_column(String, default="")
    device_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    device_name: Mapped[str] = mapped_column(String, default="")
    device_id: Mapped[str] = mapped_column(String, default="")
    detail: Mapped[str] = mapped_column(String, default="")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    agent_token: Mapped[str] = mapped_column(String, default="")

    devices: Mapped[list["Device"]] = relationship("Device", back_populates="agent")


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        Index("uq_device_id", "device_id", unique=True, sqlite_where=text("device_id != ''")),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    device_id: Mapped[str] = mapped_column(String, default="")
    serial_number: Mapped[str] = mapped_column(String, default="")
    revision: Mapped[str] = mapped_column(String, default="")
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    location: Mapped[str] = mapped_column(String, default="")
    current_notes: Mapped[str] = mapped_column(String, default="")
    agent_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    device_ip: Mapped[str] = mapped_column(String, default="")
    host_ip: Mapped[str | None] = mapped_column(String, nullable=True)
    features: Mapped[str] = mapped_column(String, default="{}")  # JSON
    jtag_port: Mapped[int] = mapped_column(Integer, default=3121)
    ssh_user: Mapped[str] = mapped_column(String, default="root")
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    power_script: Mapped[str] = mapped_column(String, default="")
    power_args: Mapped[str] = mapped_column(String, default="{}")  # JSON
    usb_device: Mapped[str] = mapped_column(String, default="")
    uart_device: Mapped[str] = mapped_column(String, default="")
    sdmux_control: Mapped[str] = mapped_column(String, default="")
    sdmux_sdcard: Mapped[str] = mapped_column(String, default="")
    access_control: Mapped[str] = mapped_column(String, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    deployed_version: Mapped[str] = mapped_column(String, default="")

    agent: Mapped["Agent | None"] = relationship("Agent", back_populates="devices")
    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="device")
    tools: Mapped[list["Tool"]] = relationship("Tool", back_populates="device", cascade="all, delete-orphan", foreign_keys="Tool.device_id")


class Booking(Base):
    __tablename__ = "bookings"

    __table_args__ = (
        Index(
            "uq_active_booking",
            "device_id",
            unique=True,
            sqlite_where=text("active = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    device_id: Mapped[str] = mapped_column(
        String, ForeignKey("devices.id"), nullable=False
    )
    username: Mapped[str] = mapped_column(String, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    extended: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    release_reason: Mapped[str] = mapped_column(String, default="")
    comment: Mapped[str] = mapped_column(String, default="")
    setup_id: Mapped[str | None] = mapped_column(String, nullable=True)
    setup_name: Mapped[str] = mapped_column(String, default="")

    device: Mapped["Device"] = relationship("Device", back_populates="bookings")


class Tool(Base):
    __tablename__ = "tools"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    device_id: Mapped[str] = mapped_column(String, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, default="")
    connection: Mapped[str] = mapped_column(String, default="usb")
    connection_detail: Mapped[str] = mapped_column(String, default="")
    notes: Mapped[str] = mapped_column(String, default="")

    device: Mapped["Device"] = relationship("Device", back_populates="tools", foreign_keys="[Tool.device_id]")
