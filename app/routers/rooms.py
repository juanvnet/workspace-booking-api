"""Rooms: every logged-in user can read them, only admins can change them."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, func, select

from app.auth import get_current_admin, get_current_user
from app.database import SessionDep
from app.models import Booking, Room, RoomCreate, RoomPublic, RoomUpdate

router = APIRouter(prefix="/rooms", tags=["rooms"], dependencies=[Depends(get_current_user)])

admin_only = [Depends(get_current_admin)]


def get_room(session: Session, room_id: int) -> Room:
    room = session.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    return room


def check_name_is_free(session: Session, name: str) -> None:
    """Room names are unique without taking uppercase/lowercase into account."""
    existing = session.exec(select(Room).where(func.lower(Room.name) == name.lower())).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Room name already used")


@router.get("", response_model=list[RoomPublic])
def list_rooms(
    session: SessionDep,
    min_capacity: Annotated[int | None, Query(gt=0)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(gt=0, le=100)] = 20,
) -> list[Room]:
    """List only active rooms, optionally only those with at least `min_capacity` seats."""
    query = select(Room).where(Room.is_active)
    if min_capacity is not None:
        query = query.where(Room.capacity >= min_capacity)
    return list(session.exec(query.order_by(Room.name).offset(offset).limit(limit)))


@router.get("/{room_id}", response_model=RoomPublic)
def read_room(room_id: int, session: SessionDep) -> Room:
    return get_room(session, room_id)


@router.post(
    "", response_model=RoomPublic, status_code=status.HTTP_201_CREATED, dependencies=admin_only
)
def create_room(room_in: RoomCreate, session: SessionDep) -> Room:
    check_name_is_free(session, room_in.name)
    room = Room.model_validate(room_in)
    session.add(room)
    session.commit()
    session.refresh(room)
    return room


@router.patch("/{room_id}", response_model=RoomPublic, dependencies=admin_only)
def update_room(room_id: int, room_in: RoomUpdate, session: SessionDep) -> Room:
    """Change only the fields that are sent. Use `is_active: false` to retire a room."""
    room = get_room(session, room_id)
    changes = room_in.model_dump(exclude_unset=True, exclude_none=True)
    # Only check the name if it really changes (fixing its uppercase/lowercase is allowed)
    if "name" in changes and changes["name"].lower() != room.name.lower():
        check_name_is_free(session, changes["name"])
    room.sqlmodel_update(changes)
    session.add(room)
    session.commit()
    session.refresh(room)
    return room


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=admin_only)
def delete_room(room_id: int, session: SessionDep) -> None:
    """Delete a room. Rooms with bookings cannot be deleted, only deactivated."""
    room = get_room(session, room_id)
    if session.exec(select(Booking).where(Booking.room_id == room_id)).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Room has bookings, deactivate it instead",
        )
    session.delete(room)
    session.commit()
