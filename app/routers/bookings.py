"""Bookings: reserve a room for a time range, list, read and cancel bookings"""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from sqlmodel import Session, select

from app.auth import CurrentUser
from app.database import SessionDep
from app.models import Booking, BookingCreate, BookingPublic, Room, User

router = APIRouter(prefix="/bookings", tags=["bookings"])

logger = logging.getLogger(__name__)


def send_confirmation(user_id: int, booking_id: int) -> None:
    """Runs in the background after the response. A real app would send an email here"""
    logger.info(f"Booking {booking_id} confirmed, notification sent to user {user_id}")


def get_booking(session: Session, booking_id: int, user: User) -> Booking:
    """Users can only access their own bookings; admins can access all of them"""
    booking = session.get(Booking, booking_id)
    if booking is None or (booking.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return booking


@router.post("", response_model=BookingPublic, status_code=status.HTTP_201_CREATED)
def create_booking(
    booking_in: BookingCreate,
    session: SessionDep,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> Booking:
    room = session.get(Room, booking_in.room_id)
    if room is None or not room.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")

    if booking_in.start_at <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Bookings must start in the future",
        )

    # Two time ranges overlap when each one starts before the other one ends
    overlapping = session.exec(
        select(Booking).where(
            Booking.room_id == booking_in.room_id,
            Booking.status == "confirmed",
            Booking.start_at < booking_in.end_at,
            Booking.end_at > booking_in.start_at,
        )
    ).first()
    if overlapping is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Room is already booked at that time"
        )

    booking = Booking.model_validate(booking_in, update={"user_id": user.id})
    session.add(booking)
    session.commit()
    session.refresh(booking)

    background_tasks.add_task(send_confirmation, user.id, booking.id)
    return booking


@router.get("", response_model=list[BookingPublic])
def list_bookings(
    session: SessionDep,
    user: CurrentUser,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(gt=0, le=100)] = 20,
) -> list[Booking]:
    """Your own bookings, ordered by start time. Admins see the bookings of all users"""
    query = select(Booking)
    if not user.is_admin:
        query = query.where(Booking.user_id == user.id)
    return list(session.exec(query.order_by(Booking.start_at).offset(offset).limit(limit)))


@router.get("/{booking_id}", response_model=BookingPublic)
def read_booking(booking_id: int, session: SessionDep, user: CurrentUser) -> Booking:
    return get_booking(session, booking_id, user)


@router.post("/{booking_id}/cancel", response_model=BookingPublic)
def cancel_booking(booking_id: int, session: SessionDep, user: CurrentUser) -> Booking:
    """Cancel a booking. It is kept with status "cancelled" and the slot becomes free"""
    booking = get_booking(session, booking_id, user)
    if booking.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Booking already cancelled"
        )

    booking.status = "cancelled"
    session.add(booking)
    session.commit()
    session.refresh(booking)
    return booking
