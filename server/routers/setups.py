import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth import require_user
from ..database import get_db
from ..models import Board, Booking, Setup, SetupBoard
from ..schemas import BookSetupIn, BookingOut, SetupBoardOut, SetupBookingOut, SetupIn, SetupOut, SetupUpdate

router = APIRouter(prefix="/setups", tags=["setups"])


def _now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _load_setup(setup_id: str, db: AsyncSession) -> Setup:
    result = await db.execute(
        select(Setup)
        .where(Setup.id == setup_id)
        .options(
            selectinload(Setup.setup_boards).selectinload(SetupBoard.board).selectinload(Board.agent),
            selectinload(Setup.setup_boards).selectinload(SetupBoard.board).selectinload(Board.bookings),
        )
    )
    setup = result.scalar_one_or_none()
    if setup is None:
        raise HTTPException(status_code=404, detail="Setup not found")
    return setup


def _board_agent_online(board: Board) -> bool:
    if not board.agent:
        return False
    return (_now_utc() - board.agent.last_seen).total_seconds() < 90


async def _build_setup_out(setup: Setup, db: AsyncSession) -> SetupOut:
    board_outs = []
    for sb in setup.setup_boards:
        b = sb.board
        active_bk = next((bk for bk in b.bookings if bk.active), None)
        board_outs.append(SetupBoardOut(
            board_id=b.id,
            board_name=b.name,
            device_id=b.device_id,
            location=b.location,
            agent_online=_board_agent_online(b),
            active_booking_username=active_bk.username if active_bk else None,
            active_booking_setup_name=active_bk.setup_name if active_bk else None,
        ))

    all_available = all(
        bof.active_booking_username is None and bof.agent_online
        for bof in board_outs
    )

    result = await db.execute(
        select(Booking).where(
            Booking.setup_id == setup.id,
            Booking.active == True,
        )
    )
    active_setup_bookings = result.scalars().all()
    active_booking_out = None
    if len(active_setup_bookings) == len(setup.setup_boards) and active_setup_bookings:
        bk = active_setup_bookings[0]
        active_booking_out = SetupBookingOut(
            username=bk.username,
            start_time=bk.start_time,
            end_time=bk.end_time,
        )

    return SetupOut(
        id=setup.id,
        name=setup.name,
        description=setup.description,
        created_at=setup.created_at,
        boards=board_outs,
        all_available=all_available,
        active_booking=active_booking_out,
    )


@router.get("", response_model=list[SetupOut])
async def list_setups(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Setup).options(
            selectinload(Setup.setup_boards).selectinload(SetupBoard.board).selectinload(Board.agent),
            selectinload(Setup.setup_boards).selectinload(SetupBoard.board).selectinload(Board.bookings),
        )
    )
    setups = result.scalars().all()
    return [await _build_setup_out(s, db) for s in setups]


@router.post("", response_model=SetupOut, status_code=201)
async def create_setup(
    body: SetupIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    setup = Setup(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        created_at=_now_utc(),
    )
    db.add(setup)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=422, detail="Setup name is already in use")

    for board_id in body.board_ids:
        board_result = await db.execute(select(Board).where(Board.id == board_id))
        if board_result.scalar_one_or_none() is None:
            await db.rollback()
            raise HTTPException(status_code=404, detail=f"Board {board_id} not found")
        db.add(SetupBoard(setup_id=setup.id, board_id=board_id))

    await db.commit()
    setup = await _load_setup(setup.id, db)
    return await _build_setup_out(setup, db)


@router.patch("/{setup_id}", response_model=SetupOut)
async def update_setup(
    setup_id: str,
    body: SetupUpdate,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    setup = await _load_setup(setup_id, db)
    if body.name is not None:
        setup.name = body.name
    if body.description is not None:
        setup.description = body.description
    if body.board_ids is not None:
        for sb in list(setup.setup_boards):
            await db.delete(sb)
        await db.flush()
        for board_id in body.board_ids:
            board_result = await db.execute(select(Board).where(Board.id == board_id))
            if board_result.scalar_one_or_none() is None:
                await db.rollback()
                raise HTTPException(status_code=404, detail=f"Board {board_id} not found")
            db.add(SetupBoard(setup_id=setup.id, board_id=board_id))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=422, detail="Setup name is already in use")
    setup = await _load_setup(setup_id, db)
    return await _build_setup_out(setup, db)


@router.delete("/{setup_id}", status_code=204)
async def delete_setup(
    setup_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    setup = await _load_setup(setup_id, db)
    result = await db.execute(
        select(Booking).where(Booking.setup_id == setup_id, Booking.active == True)
    )
    if result.scalars().first():
        raise HTTPException(status_code=409, detail="Setup has an active booking; release it first")
    await db.delete(setup)
    await db.commit()


@router.post("/{setup_id}/book", response_model=list[BookingOut])
async def book_setup(
    setup_id: str,
    body: BookSetupIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    setup = await _load_setup(setup_id, db)

    if not setup.setup_boards:
        raise HTTPException(status_code=400, detail="Setup has no devices")

    blocked = []
    for sb in setup.setup_boards:
        b = sb.board
        active_bk = next((bk for bk in b.bookings if bk.active), None)
        if active_bk:
            blocked.append(f"{b.name} (booked by {active_bk.username})")
    if blocked:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot book setup — devices unavailable: {', '.join(blocked)}",
        )

    now = _now_utc()
    end = now + timedelta(hours=body.duration_hours)
    bookings = []
    for sb in setup.setup_boards:
        bk = Booking(
            id=str(uuid.uuid4()),
            board_id=sb.board_id,
            username=user,
            start_time=now,
            end_time=end,
            extended=False,
            active=True,
            release_reason="",
            comment=body.comment,
            setup_id=setup.id,
            setup_name=setup.name,
        )
        db.add(bk)
        bookings.append(bk)

    await db.commit()
    for bk in bookings:
        await db.refresh(bk)

    return [
        BookingOut(
            id=bk.id,
            board_id=bk.board_id,
            board_name=next(sb.board.name for sb in setup.setup_boards if sb.board_id == bk.board_id),
            username=bk.username,
            start_time=bk.start_time,
            end_time=bk.end_time,
            extended=bk.extended,
            active=bk.active,
            release_reason=bk.release_reason,
            setup_id=bk.setup_id,
            setup_name=bk.setup_name,
        )
        for bk in bookings
    ]


@router.delete("/{setup_id}/booking", status_code=204)
async def release_setup_booking(
    setup_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    result = await db.execute(
        select(Booking).where(
            Booking.setup_id == setup_id,
            Booking.active == True,
        )
    )
    active_bookings = result.scalars().all()
    if not active_bookings:
        raise HTTPException(status_code=404, detail="No active booking found for this setup")

    for bk in active_bookings:
        if bk.username != user:
            raise HTTPException(status_code=403, detail="You can only release your own setup bookings")

    for bk in active_bookings:
        bk.active = False
        bk.release_reason = "manual"

    await db.commit()
