import json
import queue
from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from reservations.events import add_client, remove_client
from reservations.models import Reservation, ReservationHold, Resource
from reservations.services import get_slot_key_from_times, get_slot_times


class ReservationApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        ReservationHold.objects.all().delete()
        self.resource = Resource.objects.create(name="Meeting Room")
        self.user = get_user_model().objects.create_user(
            username="john",
            password="pass12345",
        )
        self.admin = get_user_model().objects.get(username="admin")

    def login(self, username="john"):
        password = "Admin12345" if username == "admin" else "pass12345"
        response = self.client.post(
            "/api/auth/login/",
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
        )
        return response.json()["token"]

    def auth_header(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_register_returns_token(self):
        response = self.client.post(
            "/api/auth/register/",
            data=json.dumps({"username": "mary", "password": "pass12345"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("token", response.json())

    def test_user_cannot_create_conflicting_reservation(self):
        token = self.login()
        payload = {
            "resource_id": self.resource.id,
            "start_time": "2026-08-03T10:00:00Z",
            "end_time": "2026-08-03T11:00:00Z",
        }

        first_response = self.client.post(
            "/api/reservations/",
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth_header(token),
        )
        second_response = self.client.post(
            "/api/reservations/",
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth_header(token),
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 400)

    def test_restaurant_slot_becomes_full(self):
        token = self.login()
        payload = {
            "date": "2026-08-03",
            "slot": "09-12",
        }

        hold_response = self.client.post(
            "/api/holds/",
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth_header(token),
        )

        first_response = self.client.post(
            "/api/reservations/",
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth_header(token),
        )
        second_response = self.client.post(
            "/api/reservations/",
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth_header(token),
        )
        availability_response = self.client.get(
            "/api/availability/?date=2026-08-03",
            **self.auth_header(token),
        )

        full_slot = [
            slot for slot in availability_response.json()["slots"]
            if slot["key"] == "09-12"
        ][0]
        self.assertEqual(hold_response.status_code, 201)
        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(first_response.json()["reservation"]["status"], "CONFIRMED")
        self.assertEqual(second_response.status_code, 400)
        self.assertTrue(full_slot["is_full"])

    def test_selected_slot_is_visible_before_confirm(self):
        token = self.login()
        payload = {
            "date": "2026-08-03",
            "slot": "12-15",
        }

        hold_response = self.client.post(
            "/api/holds/",
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth_header(token),
        )
        availability_response = self.client.get(
            "/api/availability/?date=2026-08-03",
            **self.auth_header(token),
        )

        selected_slot = [
            slot for slot in availability_response.json()["slots"]
            if slot["key"] == "12-15"
        ][0]
        self.assertEqual(hold_response.status_code, 201)
        self.assertTrue(selected_slot["is_selected"])
        self.assertTrue(selected_slot["held_by_me"])

    def test_other_users_selected_slot_is_not_marked_as_mine(self):
        token = self.login()
        other_user = get_user_model().objects.create_user(
            username="mary",
            password="pass12345",
        )
        ReservationHold.objects.create(
            user=other_user,
            date="2026-08-03",
            slot="12-15",
            expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )

        response = self.client.get(
            "/api/availability/?date=2026-08-03",
            **self.auth_header(token),
        )

        selected_slot = [
            slot for slot in response.json()["slots"]
            if slot["key"] == "12-15"
        ][0]
        self.assertEqual(response.status_code, 200)
        self.assertTrue(selected_slot["is_selected"])
        self.assertFalse(selected_slot["held_by_me"])

    def test_empty_availability_has_no_selected_slots(self):
        token = self.login()

        response = self.client.get(
            "/api/availability/?date=2026-08-04",
            **self.auth_header(token),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(any(slot["is_selected"] for slot in response.json()["slots"]))

    def test_user_can_release_selected_slot(self):
        token = self.login()
        payload = {
            "date": "2026-08-03",
            "slot": "15-18",
        }

        self.client.post(
            "/api/holds/",
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth_header(token),
        )
        release_response = self.client.post(
            "/api/holds/release/",
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth_header(token),
        )
        availability_response = self.client.get(
            "/api/availability/?date=2026-08-03",
            **self.auth_header(token),
        )

        released_slot = [
            slot for slot in availability_response.json()["slots"]
            if slot["key"] == "15-18"
        ][0]
        self.assertEqual(release_response.status_code, 200)
        self.assertFalse(released_slot["is_selected"])

    def test_started_today_slot_is_unavailable(self):
        token = self.login()
        current_time = timezone.make_aware(datetime(2026, 8, 5, 9, 1))

        with patch("reservations.services.timezone.now", return_value=current_time):
            response = self.client.get(
                "/api/availability/?date=2026-08-05",
                **self.auth_header(token),
            )
            hold_response = self.client.post(
                "/api/holds/",
                data=json.dumps({"date": "2026-08-05", "slot": "09-12"}),
                content_type="application/json",
                **self.auth_header(token),
            )

        slots = {slot["key"]: slot for slot in response.json()["slots"]}
        self.assertEqual(response.status_code, 200)
        self.assertTrue(slots["09-12"]["is_full"])
        self.assertTrue(slots["09-12"]["is_unavailable"])
        self.assertFalse(slots["12-15"]["is_full"])
        self.assertEqual(hold_response.status_code, 400)

    def test_switching_selected_slot_publishes_released_slot_details(self):
        token = self.login()
        first_payload = {"date": "2026-08-03", "slot": "12-15"}
        second_payload = {"date": "2026-08-03", "slot": "15-18"}
        self.client.post(
            "/api/holds/",
            data=json.dumps(first_payload),
            content_type="application/json",
            **self.auth_header(token),
        )
        client_queue = add_client()

        try:
            self.client.post(
                "/api/holds/",
                data=json.dumps(second_payload),
                content_type="application/json",
                **self.auth_header(token),
            )
            release_event = client_queue.get(timeout=1)
            create_event = client_queue.get(timeout=1)
        except queue.Empty:
            self.fail("Expected slot switch events to be published.")
        finally:
            remove_client(client_queue)

        self.assertEqual(release_event["event"], "slot.hold_released")
        self.assertEqual(release_event["data"]["date"], "2026-08-03")
        self.assertEqual(release_event["data"]["slot"], "12-15")
        self.assertEqual(create_event["event"], "slot.hold_created")
        self.assertEqual(create_event["data"]["slot"], "15-18")

    def test_reservation_event_payload_has_slot_key(self):
        start_time, end_time = get_slot_times("2026-08-03", "12-15")
        reservation = Reservation.objects.create(
            user=self.user,
            resource=self.resource,
            start_time=start_time,
            end_time=end_time,
        )

        slot_key = get_slot_key_from_times(reservation.start_time, reservation.end_time)

        self.assertEqual(slot_key, "12-15")

    def test_admin_can_change_reservation_status(self):
        token = self.login("admin")
        reservation = Reservation.objects.create(
            user=self.user,
            resource=self.resource,
            start_time="2026-08-03T10:00:00Z",
            end_time="2026-08-03T11:00:00Z",
        )

        response = self.client.patch(
            f"/api/admin/reservations/{reservation.id}/status/",
            data=json.dumps({"status": "CONFIRMED"}),
            content_type="application/json",
            **self.auth_header(token),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reservation"]["status"], "CONFIRMED")
