from datetime import UTC, datetime

from app.models import Booking

ROOMS_URL = "/api/v1/rooms"
NEW_ROOM = {"name": "Zen Zone", "location": "Bern Office", "capacity": 4}


# ---------- List and read ----------


def test_list_rooms(client, user_headers, room):
    response = client.get(ROOMS_URL, headers=user_headers)

    assert response.status_code == 200
    assert response.json()[0]["name"] == room.name


def test_list_rooms_without_token_fails(client):
    response = client.get(ROOMS_URL)

    assert response.status_code == 401


def test_list_rooms_by_min_capacity(client, user_headers, room):
    response = client.get(ROOMS_URL, params={"min_capacity": 10}, headers=user_headers)

    assert response.json() == []  # the room only has 8 seats


def test_inactive_rooms_are_not_listed(client, user_headers, admin_headers, room):
    client.patch(f"{ROOMS_URL}/{room.id}", json={"is_active": False}, headers=admin_headers)

    response = client.get(ROOMS_URL, headers=user_headers)

    assert response.json() == []


def test_read_room(client, user_headers, room):
    response = client.get(f"{ROOMS_URL}/{room.id}", headers=user_headers)

    assert response.status_code == 200
    assert response.json()["name"] == room.name


def test_read_unknown_room_fails(client, user_headers):
    response = client.get(f"{ROOMS_URL}/999", headers=user_headers)

    assert response.status_code == 404


# ---------- Create ----------


def test_create_room(client, admin_headers):
    response = client.post(ROOMS_URL, json=NEW_ROOM, headers=admin_headers)

    assert response.status_code == 201
    assert response.json()["name"] == "Zen Zone"
    assert response.json()["is_active"] is True


def test_create_room_as_regular_user_fails(client, user_headers):
    response = client.post(ROOMS_URL, json=NEW_ROOM, headers=user_headers)

    assert response.status_code == 403


def test_create_room_with_existing_name_fails(client, admin_headers, room):
    data = {**NEW_ROOM, "name": room.name}

    response = client.post(ROOMS_URL, json=data, headers=admin_headers)

    assert response.status_code == 409


def test_create_room_with_existing_name_in_other_case_fails(client, admin_headers, room):
    data = {**NEW_ROOM, "name": room.name.upper()}  # "HAMMERHEAD" is the same name

    response = client.post(ROOMS_URL, json=data, headers=admin_headers)

    assert response.status_code == 409


def test_create_room_with_zero_capacity_fails(client, admin_headers):
    response = client.post(ROOMS_URL, json={**NEW_ROOM, "capacity": 0}, headers=admin_headers)

    assert response.status_code == 422


def test_create_room_with_too_much_capacity_fails(client, admin_headers):
    response = client.post(ROOMS_URL, json={**NEW_ROOM, "capacity": 51}, headers=admin_headers)

    assert response.status_code == 422


# ---------- Update ----------


def test_update_room(client, admin_headers, room):
    response = client.patch(f"{ROOMS_URL}/{room.id}", json={"capacity": 12}, headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["capacity"] == 12
    assert response.json()["name"] == room.name  # fields not sent stay the same


def test_update_room_as_regular_user_fails(client, user_headers, room):
    response = client.patch(f"{ROOMS_URL}/{room.id}", json={"capacity": 12}, headers=user_headers)

    assert response.status_code == 403


# ---------- Delete ----------


def test_delete_room(client, admin_headers, room):
    response = client.delete(f"{ROOMS_URL}/{room.id}", headers=admin_headers)

    assert response.status_code == 204
    assert client.get(f"{ROOMS_URL}/{room.id}", headers=admin_headers).status_code == 404


def test_delete_room_with_bookings_fails(client, session, admin_headers, user, room):
    booking = Booking(
        room_id=room.id,
        user_id=user.id,
        title="Planning",
        start_at=datetime(2030, 1, 10, 9, 0, tzinfo=UTC),
        end_at=datetime(2030, 1, 10, 10, 0, tzinfo=UTC),
    )
    session.add(booking)
    session.commit()

    response = client.delete(f"{ROOMS_URL}/{room.id}", headers=admin_headers)

    assert response.status_code == 409
