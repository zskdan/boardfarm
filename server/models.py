from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    boards: Mapped[list["Board"]] = relationship("Board", back_populates="agent")


class Board(Base):
    __tablename__ = "boards"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    location: Mapped[str] = mapped_column(String, default="")
    agent_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    host_ip: Mapped[str | None] = mapped_column(String, nullable=True)
    features: Mapped[str] = mapped_column(String, default="{}")  # JSON
    jtag_port: Mapped[int] = mapped_column(Integer, default=3121)
    uart_tcp_port: Mapped[int] = mapped_column(Integer, default=5555)
    ssh_user: Mapped[str] = mapped_column(String, default="root")
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    power_script: Mapped[str] = mapped_column(String, default="")
    power_args: Mapped[str] = mapped_column(String, default="{}")  # JSON
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    agent: Mapped["Agent | None"] = relationship("Agent", back_populates="boards")
    tools: Mapped[list["Tool"]] = relationship(
        "Tool", back_populates="board", cascade="all, delete-orphan"
    )
    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="board")


class Tool(Base):
    __tablename__ = "tools"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    board_id: Mapped[str] = mapped_column(
        String, ForeignKey("boards.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, default="")
    connection: Mapped[str] = mapped_column(String, default="usb")
    connection_detail: Mapped[str] = mapped_column(String, default="")
    notes: Mapped[str] = mapped_column(String, default="")

    board: Mapped["Board"] = relationship("Board", back_populates="tools")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    board_id: Mapped[str] = mapped_column(
        String, ForeignKey("boards.id"), nullable=False
    )
    username: Mapped[str] = mapped_column(String, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    extended: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    release_reason: Mapped[str] = mapped_column(String, default="")

    board: Mapped["Board"] = relationship("Board", back_populates="bookings")
