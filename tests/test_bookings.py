from datetime import UTC, datetime, timedelta, timezone

import pytest

BOOKINGS_URL = "/api/v1/bookings"


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


def test_create_booking_ending_before_start_fails(client, user_headers, room, tomorrow_9am):
    data = booking_data(room, tomorrow_9am, hours=-1)

    response = client.post(BOOKINGS_URL, json=data, headers=user_headers)

    assert response.status_code == 422


def test_create_booking_for_unknown_room_fails(client, user_headers, room, tomorrow_9am):
    data = {**booking_data(room, tomorrow_9am), "room_id": 999}

    response = client.post(BOOKINGS_URL, json=data, headers=user_headers)

    assert response.status_code == 404


# ---------- Overlaps (the `booking` fixture is from 09:00 to 10:00) ----------


def test_overlapping_booking_fails(client, other_user_headers, booking, room, tomorrow_9am):
    data = booking_data(room, tomorrow_9am + timedelta(minutes=30))  # 09:30-10:30

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
