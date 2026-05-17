import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth import require_auth
from ..database import get_db
from ..models import Agent, Board, Booking
from ..schemas import BoardIn, BoardOut, BoardUpdate, BookingOut, ToolOut

router = APIRouter(prefix="/boards", tags=["boards"])


def _now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _build_board_out(board: Board, db: AsyncSession) -> BoardOut:
    agent_online = False
    if board.agent:
        delta = (_now_utc() - board.agent.last_seen).total_seconds()
        agent_online = delta < 90

    active_booking = None
    for bk in board.bookings:
        if bk.active:
            active_booking = BookingOut(
                id=bk.id,
                board_id=bk.board_id,
                board_name=board.name,
                username=bk.username,
                start_time=bk.start_time,
                end_time=bk.end_time,
                extended=bk.extended,
                active=bk.active,
                release_reason=bk.release_reason,
            )
            break

    tools = [ToolOut.model_validate(t) for t in board.tools]

    return BoardOut(
        id=board.id,
        name=board.name,
        description=board.description,
        location=board.location,
        current_notes=board.current_notes,
        agent_id=board.agent_id,
        host_ip=board.host_ip,
        features=json.loads(board.features) if board.features else {},
        jtag_port=board.jtag_port,
        uart_tcp_port=board.uart_tcp_port,
        ssh_user=board.ssh_user,
        ssh_port=board.ssh_port,
        power_script=board.power_script,
        power_args=json.loads(board.power_args) if board.power_args else {},
        enabled=board.enabled,
        agent_online=agent_online,
        active_booking=active_booking,
        tools=tools,
    )


async def _load_board(board_id: str, db: AsyncSession) -> Board:
    result = await db.execute(
        select(Board)
        .where(Board.id == board_id)
        .options(
            selectinload(Board.agent),
            selectinload(Board.tools),
            selectinload(Board.bookings),
        )
    )
    board = result.scalar_one_or_none()
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")
    return board


@router.get("", response_model=list[BoardOut])
async def list_boards(
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_auth),
):
    result = await db.execute(
        select(Board).options(
            selectinload(Board.agent),
            selectinload(Board.tools),
            selectinload(Board.bookings),
        )
    )
    boards = result.scalars().all()
    return [await _build_board_out(b, db) for b in boards]


@router.get("/{board_id}", response_model=BoardOut)
async def get_board(
    board_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_auth),
):
    board = await _load_board(board_id, db)
    return await _build_board_out(board, db)


@router.post("", response_model=BoardOut, status_code=201)
async def create_board(
    body: BoardIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_auth),
):
    board = Board(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        location=body.location,
        current_notes=body.current_notes,
        features=json.dumps(body.features),
        jtag_port=body.jtag_port,
        uart_tcp_port=body.uart_tcp_port,
        ssh_user=body.ssh_user,
        ssh_port=body.ssh_port,
        power_script=body.power_script,
        power_args=json.dumps(body.power_args),
        enabled=body.enabled,
    )
    db.add(board)
    await db.commit()
    board = await _load_board(board.id, db)
    return await _build_board_out(board, db)


@router.patch("/{board_id}", response_model=BoardOut)
async def update_board(
    board_id: str,
    body: BoardUpdate,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_auth),
):
    board = await _load_board(board_id, db)
    for field, value in body.model_dump(exclude_none=True).items():
        if field in ("features", "power_args"):
            setattr(board, field, json.dumps(value))
        else:
            setattr(board, field, value)
    await db.commit()
    board = await _load_board(board_id, db)
    return await _build_board_out(board, db)


@router.delete("/{board_id}", status_code=204)
async def delete_board(
    board_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_auth),
):
    board = await _load_board(board_id, db)
    for bk in board.bookings:
        if bk.active:
            raise HTTPException(
                status_code=409, detail="Board has an active booking; release it first"
            )
    await db.delete(board)
    await db.commit()
