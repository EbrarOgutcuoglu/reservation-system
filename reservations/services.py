from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.dateparse import parse_datetime

from .events import publish_event
from .models import Reservation, Resource
from .serializers import reservation_to_dict

RESTAURANT_RESOURCE_NAME = "Rezervem Restaurant"

RESTAURANT_SLOTS = [
    {"key": "09-12", "label": "09:00 - 12:00", "start_hour": 9, "end_hour": 12},
    {"key": "12-15", "label": "12:00 - 15:00", "start_hour": 12, "end_hour": 15},
    {"key": "15-18", "label": "15:00 - 18:00", "start_hour": 15, "end_hour": 18},
    {"key": "18-21", "label": "18:00 - 21:00", "start_hour": 18, "end_hour": 21},
    {"key": "21-24", "label": "21:00 - 00:00", "start_hour": 21, "end_hour": 24},
]


def parse_time(value, field_name):
    parsed = parse_datetime(value or "")
    if not parsed:
        raise ValueError(f"{field_name} must be a valid datetime.")
    return parsed


def validate_time_range(start_time, end_time):
    if end_time <= start_time:
        raise ValueError("end_time must be after start_time.")


def has_conflict(resource, start_time, end_time, reservation_id=None):
    reservations = Reservation.objects.filter(
        resource=resource,
        status__in=[Reservation.Status.PENDING, Reservation.Status.CONFIRMED],
        start_time__lt=end_time,
        end_time__gt=start_time,
    )
    if reservation_id:
        reservations = reservations.exclude(id=reservation_id)
    return reservations.exists()


def get_restaurant_resource():
    resource, _ = Resource.objects.get_or_create(
        name=RESTAURANT_RESOURCE_NAME,
        defaults={
            "description": "Restaurant table reservation area.",
            "is_active": True,
        },
    )
    return resource


def get_slot(slot_key):
    for slot in RESTAURANT_SLOTS:
        if slot["key"] == slot_key:
            return slot
    raise ValueError("Reservation slot is invalid.")


def get_slot_times(date_value, slot_key):
    selected_date = parse_date(date_value or "")
    if not selected_date:
        raise ValueError("date must be a valid date.")

    slot = get_slot(slot_key)
    start_time = timezone.make_aware(
        datetime.combine(selected_date, time(hour=slot["start_hour"]))
    )

    if slot["end_hour"] == 24:
        end_time = timezone.make_aware(datetime.combine(selected_date, time(hour=0))) + timedelta(days=1)
    else:
        end_time = timezone.make_aware(datetime.combine(selected_date, time(hour=slot["end_hour"])))

    return start_time, end_time


def get_restaurant_availability(date_value):
    resource = get_restaurant_resource()
    slots = []
    for slot in RESTAURANT_SLOTS:
        start_time, end_time = get_slot_times(date_value, slot["key"])
        is_full = has_conflict(resource, start_time, end_time)
        slots.append(
            {
                "key": slot["key"],
                "label": slot["label"],
                "is_full": is_full,
            }
        )
    return slots


@transaction.atomic
def create_reservation(user, data):
    if "date" in data and "slot" in data:
        resource = get_restaurant_resource()
        start_time, end_time = get_slot_times(data.get("date"), data.get("slot"))
    else:
        resource = Resource.objects.filter(id=data.get("resource_id"), is_active=True).first()
        if not resource:
            raise ValueError("Resource was not found.")
        start_time = parse_time(data.get("start_time"), "start_time")
        end_time = parse_time(data.get("end_time"), "end_time")

    validate_time_range(start_time, end_time)

    # Lock resource row while checking availability.
    Resource.objects.select_for_update().get(id=resource.id)
    if has_conflict(resource, start_time, end_time):
        raise ValueError("Reservation time conflicts with another reservation.")

    reservation = Reservation.objects.create(
        user=user,
        resource=resource,
        start_time=start_time,
        end_time=end_time,
        note=data.get("note", ""),
    )
    publish_reservation_change("reservation.created", reservation)
    return reservation


@transaction.atomic
def update_reservation(reservation, data):
    resource = reservation.resource
    if "resource_id" in data:
        resource = Resource.objects.filter(id=data.get("resource_id"), is_active=True).first()
        if not resource:
            raise ValueError("Resource was not found.")

    start_time = reservation.start_time
    end_time = reservation.end_time
    if "start_time" in data:
        start_time = parse_time(data.get("start_time"), "start_time")
    if "end_time" in data:
        end_time = parse_time(data.get("end_time"), "end_time")

    validate_time_range(start_time, end_time)
    Resource.objects.select_for_update().get(id=resource.id)
    if has_conflict(resource, start_time, end_time, reservation_id=reservation.id):
        raise ValueError("Reservation time conflicts with another reservation.")

    reservation.resource = resource
    reservation.start_time = start_time
    reservation.end_time = end_time
    reservation.note = data.get("note", reservation.note)
    reservation.save()
    publish_reservation_change("reservation.updated", reservation)
    return reservation


def cancel_reservation(reservation):
    reservation.status = Reservation.Status.CANCELLED
    reservation.save(update_fields=["status", "updated_at"])
    publish_reservation_change("reservation.cancelled", reservation)
    return reservation


def change_reservation_status(reservation, status):
    allowed_statuses = [choice[0] for choice in Reservation.Status.choices]
    if status not in allowed_statuses:
        raise ValueError("Reservation status is invalid.")

    reservation.status = status
    reservation.save(update_fields=["status", "updated_at"])
    publish_reservation_change("reservation.status_changed", reservation)
    return reservation


def publish_reservation_change(event_name, reservation):
    publish_event(event_name, reservation_to_dict(reservation))
