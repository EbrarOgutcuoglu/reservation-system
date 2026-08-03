import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from reservations.models import Reservation, Resource


class ReservationApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.resource = Resource.objects.create(name="Meeting Room")
        self.user = get_user_model().objects.create_user(
            username="john",
            password="pass12345",
        )
        self.admin = get_user_model().objects.create_user(
            username="admin",
            password="pass12345",
            is_staff=True,
        )

    def login(self, username="john"):
        response = self.client.post(
            "/api/auth/login/",
            data=json.dumps({"username": username, "password": "pass12345"}),
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
        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 400)
        self.assertTrue(full_slot["is_full"])

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
