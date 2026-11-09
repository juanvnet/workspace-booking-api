import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import false
from sqlmodel import select

import app.routers.bookings as bookings_router
from app.models import Booking

BOOKINGS_URL = "/api/v1/bookings"


def at(day: datetime, hour: str) -> datetime:
    """The same day as `day` at `hour` ("HH:MM")"""
    hours, minutes = hour.split(":")
    return day.replace(hour=int(hours), minute=int(minutes))


def booking_data(room, start, hours=1) -> dict:
    """JSON body to book `room` from `start` for a number of hours"""
    return {
        "room_id": room.id,
        "title": "Sprint review",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(hours=hours)).isoformat(),
    }


@pytest.fixture
def booking(client, user_headers, room, tomorrow_9am) -> dict:
    """A booking made by `user`: tomorrow from 09:00 to 10:00"""
    data = booking_data(room, tomorrow_9am)
    return client.post(BOOKINGS_URL, json=data, headers=user_headers).json()


# ---------- Create ----------


def test_create_booking(booking, room):
    assert booking["room_id"] == room.id
    assert booking["status"] == "confirmed"


def test_create_booking_converts_time_to_utc(client, user_headers, room, tomorrow_9am):
    swiss_time = tomorrow_9am.replace(tzinfo=timezone(timedelta(hours=2)))  # 09:00 = 07:00 UTC

    response = client.post(BOOKINGS_URL, json=booking_data(room, swiss_time), headers=user_headers)

    assert datetime.fromisoformat(response.json()["start_at"]).hour == 7


def test_create_booking_in_the_past_fails(client, user_headers, room):
    yesterday = datetime.now(UTC) - timedelta(days=1)

    response = client.post(BOOKINGS_URL, json=booking_data(room, yesterday), headers=user_headers)

    assert response.status_code == 422


def test_create_booking_longer_than_8_hours_fails(client, user_headers, room, tomorrow_9am):
    data = booking_data(room, tomorrow_9am, hours=9)

    response = client.post(BOOKINGS_URL, json=data, headers=user_headers)

    assert response.status_code == 422


def test_create_booking_shorter_than_5_minutes_fails(client, user_headers, room, tomorrow_9am):
    data = booking_data(room, tomorrow_9am)
    data["end_at"] = (tomorrow_9am + timedelta(minutes=4)).isoformat()

    response = client.post(BOOKINGS_URL, json=data, headers=user_headers)

    assert response.status_code == 422


def test_create_booking_of_5_minutes_is_allowed(client, user_headers, room, tomorrow_9am):
    data = booking_data(room, tomorrow_9am)
    data["end_at"] = (tomorrow_9am + timedelta(minutes=5)).isoformat()

    response = client.post(BOOKINGS_URL, json=data, headers=user_headers)

    assert response.status_code == 201


def test_create_booking_of_8_hours_is_allowed(client, user_headers, room, tomorrow_9am):
    data = booking_data(room, tomorrow_9am, hours=8)

    response = client.post(BOOKINGS_URL, json=data, headers=user_headers)

    assert response.status_code == 201


def test_create_booking_ending_before_start_fails(client, user_headers, room, tomorrow_9am):
    data = booking_data(room, tomorrow_9am, hours=-1)

    response = client.post(BOOKINGS_URL, json=data, headers=user_headers)

    assert response.status_code == 422


def test_create_booking_for_unknown_room_fails(client, user_headers, room, tomorrow_9am):
    data = {**booking_data(room, tomorrow_9am), "room_id": 999}

    response = client.post(BOOKINGS_URL, json=data, headers=user_headers)

    assert response.status_code == 404


# ---------- Overlaps (the `booking` fixture is from 09:00 to 10:00) ----------


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("08:30", "09:30"),
        ("09:30", "10:30"),
        ("09:15", "09:45"),
        ("08:00", "11:00"),
        ("09:00", "10:00"),
    ],
)
def test_overlapping_booking_fails(
    client, other_user_headers, booking, room, tomorrow_9am, start, end
):
    data = booking_data(room, at(tomorrow_9am, start))
    data["end_at"] = at(tomorrow_9am, end).isoformat()

    response = client.post(BOOKINGS_URL, json=data, headers=other_user_headers)

    assert response.status_code == 409


def test_back_to_back_booking_is_allowed(client, other_user_headers, booking, room, tomorrow_9am):
    data = booking_data(room, tomorrow_9am + timedelta(hours=1))  # 10:00-11:00

    response = client.post(BOOKINGS_URL, json=data, headers=other_user_headers)

    assert response.status_code == 201


def test_cancelled_booking_frees_the_slot(
    client, user_headers, other_user_headers, booking, room, tomorrow_9am
):
    client.post(f"{BOOKINGS_URL}/{booking['id']}/cancel", headers=user_headers)

    response = client.post(
        BOOKINGS_URL, json=booking_data(room, tomorrow_9am), headers=other_user_headers
    )

    assert response.status_code == 201


def test_database_rejects_overlap_missed_by_the_api(
    client, other_user_headers, booking, room, tomorrow_9am, monkeypatch
):
    """Even if the overlap check of the API failed, the database constraint answers 409"""
    real_select = bookings_router.select
    monkeypatch.setattr(bookings_router, "select", lambda *a: real_select(*a).where(false()))
    data = booking_data(room, tomorrow_9am + timedelta(minutes=30))  # 09:30-10:30

    response = client.post(BOOKINGS_URL, json=data, headers=other_user_headers)

    assert response.status_code == 409


def test_simultaneous_bookings_of_the_same_slot(
    client, session, user_headers, room, tomorrow_9am, monkeypatch
):
    """10 requests at the same time for the same slot: only one booking is saved"""
    model_validate = Booking.model_validate

    def slow_save(*args, **kwargs):
        time.sleep(0.1)  # the moment where two requests at the same time could both pass the check
        return model_validate(*args, **kwargs)

    monkeypatch.setattr(Booking, "model_validate", slow_save)
    data = booking_data(room, tomorrow_9am)

    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(BOOKINGS_URL, json=data, headers=user_headers), range(10)
            )
        )

    assert sorted(response.status_code for response in responses) == [201] + [409] * 9
    assert len(session.exec(select(Booking)).all()) == 1


def test_second_booking_waits_until_the_first_one_is_saved(
    client, user_headers, room, tomorrow_9am, monkeypatch
):
    """The room is locked while a booking is saved: a second request for the same room waits,
    then sees the new booking and answers 409 without trying to save"""
    saves = []
    first_is_saving = threading.Event()
    let_first_finish = threading.Event()
    model_validate = Booking.model_validate

    def hold_first_save(*args, **kwargs):
        saves.append(1)
        if len(saves) == 1:
            first_is_saving.set()
            let_first_finish.wait(timeout=5)
        return model_validate(*args, **kwargs)

    monkeypatch.setattr(Booking, "model_validate", hold_first_save)
    data = booking_data(room, tomorrow_9am)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.post, BOOKINGS_URL, json=data, headers=user_headers)
        assert first_is_saving.wait(timeout=5)
        second = pool.submit(client.post, BOOKINGS_URL, json=data, headers=user_headers)
        time.sleep(0.5)  # without the lock, the second request would reach the save by now
        let_first_finish.set()

    assert first.result().status_code == 201
    assert second.result().status_code == 409
    assert len(saves) == 1


# ---------- List and read ----------


def test_users_only_see_their_own_bookings(client, user_headers, other_user_headers, booking):
    assert len(client.get(BOOKINGS_URL, headers=user_headers).json()) == 1
    assert client.get(BOOKINGS_URL, headers=other_user_headers).json() == []


def test_admin_sees_all_bookings(client, admin_headers, booking):
    assert len(client.get(BOOKINGS_URL, headers=admin_headers).json()) == 1


def test_read_booking_of_another_user_fails(client, other_user_headers, booking):
    response = client.get(f"{BOOKINGS_URL}/{booking['id']}", headers=other_user_headers)

    assert response.status_code == 404


# ---------- Cancel ----------


def test_cancel_booking(client, user_headers, booking):
    response = client.post(f"{BOOKINGS_URL}/{booking['id']}/cancel", headers=user_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_booking_twice_fails(client, user_headers, booking):
    client.post(f"{BOOKINGS_URL}/{booking['id']}/cancel", headers=user_headers)

    response = client.post(f"{BOOKINGS_URL}/{booking['id']}/cancel", headers=user_headers)

    assert response.status_code == 409


def test_cancel_booking_of_another_user_fails(client, other_user_headers, booking):
    response = client.post(f"{BOOKINGS_URL}/{booking['id']}/cancel", headers=other_user_headers)

    assert response.status_code == 404


def test_admin_can_cancel_any_booking(client, admin_headers, booking):
    response = client.post(f"{BOOKINGS_URL}/{booking['id']}/cancel", headers=admin_headers)

    assert response.status_code == 200
