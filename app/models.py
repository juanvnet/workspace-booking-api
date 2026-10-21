"""Database tables and API schemas(the shapes of the data the API receives and returns)

For each resource there is a Base class with the shared fields, the table
(table=True) and the schemas used to create, update and return it.

Datetimes are stored and returned in UTC (SQLModel converts them automatically)
"""

from datetime import UTC, datetime
from typing import Self

from pydantic import EmailStr, field_validator, model_validator
from sqlmodel import Field, SQLModel

# ---------- Users ----------


class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    full_name: str = Field(min_length=1, max_length=100)


class User(UserBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    hashed_password: str
    is_admin: bool = False


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=64)


class UserUpdate(SQLModel):
    """Fields a user can change in their own profile. is_admin can never be changed here."""

    email: EmailStr | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=8, max_length=64)


class UserPublic(UserBase):
    id: int
    is_admin: bool


# Login response (required for OAuth2)
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Rooms ----------


class RoomBase(SQLModel):
    name: str = Field(min_length=1, max_length=100, unique=True)
    location: str = Field(min_length=1, max_length=100)
    capacity: int = Field(gt=0, le=50)


class Room(RoomBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    is_active: bool = True


class RoomCreate(RoomBase):
    pass


class RoomUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    location: str | None = Field(default=None, min_length=1, max_length=100)
    capacity: int | None = Field(default=None, gt=0, le=50)
    is_active: bool | None = None


class RoomPublic(RoomBase):
    id: int
    is_active: bool


# ---------- Bookings ----------


class BookingBase(SQLModel):
    room_id: int = Field(foreign_key="room.id", index=True)
    title: str = Field(min_length=1, max_length=200)
    start_at: datetime
    end_at: datetime


class Booking(BookingBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    status: str = "confirmed"


class BookingCreate(BookingBase):
    @field_validator("start_at", "end_at")
    @classmethod
    def convert_to_utc(cls, value: datetime) -> datetime:
        """Accept any timezone and convert it to UTC. Times without timezone are taken as UTC"""
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def check_end_after_start(self) -> Self:
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be later than start_at")
        return self


class BookingPublic(BookingBase):
    id: int
    user_id: int
    status: str
