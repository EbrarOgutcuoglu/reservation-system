from datetime import datetime, time, timedelta

from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.dateparse import parse_datetime

from .events import publish_event
from .models import Reservation, ReservationHold, Resource
from .serializers import reservation_to_dict

RESTAURANT_RESOURCE_NAME = "Rezervem Restaurant"

RESTAURANT_SLOTS = [
    {"key": "09-12", "label": "09:00 - 12:00", "start_hour": 9, "end_hour": 12},
    {"key": "12-15", "label": "12:00 - 15:00", "start_hour": 12, "end_hour": 15},
    {"key": "15-18", "label": "15:00 - 18:00", "start_hour": 15, "end_hour": 18},
    {"key": "18-21", "label": "18:00 - 21:00", "start_hour": 18, "end_hour": 21},
    {"key": "21-24", "label": "21:00 - 00:00", "start_hour": 21, "end_hour": 24},
]

HOLD_MINUTES = 10


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


def cleanup_expired_holds():
    ReservationHold.objects.filter(expires_at__lte=timezone.now()).delete()


def get_active_hold(date_value, slot_key):
    selected_date = parse_date(date_value or "")
    if not selected_date:
        return None
    cleanup_expired_holds()
    return ReservationHold.objects.filter(date=selected_date, slot=slot_key).first()


@transaction.atomic
def hold_slot(user, date_value, slot_key):
    resource = get_restaurant_resource()
    start_time, end_time = get_slot_times(date_value, slot_key)
    selected_date = parse_date(date_value or "")
    if slot_has_started(start_time):
        raise ValueError("This time is no longer available.")
    if has_conflict(resource, start_time, end_time):
        raise ValueError("Reservation time conflicts with another reservation.")

    cleanup_expired_holds()
    release_user_hold(user)
    current_hold = ReservationHold.objects.select_for_update().filter(
        date=selected_date,
        slot=slot_key,
    ).first()
    if current_hold and current_hold.user_id != user.id:
        raise ValueError("This time is currently selected by another user.")

    expires_at = timezone.now() + timedelta(minutes=HOLD_MINUTES)
    if current_hold:
        current_hold.expires_at = expires_at
        current_hold.save(update_fields=["expires_at", "updated_at"])
        hold = current_hold
    else:
        try:
            hold = ReservationHold.objects.create(
                user=user,
                date=selected_date,
                slot=slot_key,
                expires_at=expires_at,
            )
        except IntegrityError as exc:
            raise ValueError("This time is currently selected by another user.") from exc

    publish_event(
        "slot.hold_created",
        {
            "date": date_value,
            "slot": slot_key,
            "user_id": user.id,
            "expires_at": expires_at.isoformat(),
        },
    )
    return hold


def release_user_hold(user, date_value=None, slot_key=None):
    cleanup_expired_holds()
    holds = ReservationHold.objects.filter(user=user)
    if date_value is not None:
        selected_date = parse_date(date_value or "")
        holds = holds.filter(date=selected_date)
    if slot_key is not None:
        holds = holds.filter(slot=slot_key)
    removed_holds = list(holds.values("date", "slot"))
    holds.delete()

    for hold in removed_holds:
        publish_event(
            "slot.hold_released",
            {
                "date": hold["date"].isoformat(),
                "slot": hold["slot"],
                "user_id": user.id,
            },
        )


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


def slot_has_started(start_time):
    local_start = timezone.localtime(start_time)
    local_now = timezone.localtime(timezone.now())
    return local_start.date() == local_now.date() and local_start <= local_now


def get_restaurant_availability(date_value, user=None):
    resource = get_restaurant_resource()
    slots = []
    for slot in RESTAURANT_SLOTS:
        start_time, end_time = get_slot_times(date_value, slot["key"])
        is_unavailable = slot_has_started(start_time)
        is_full = is_unavailable or has_conflict(resource, start_time, end_time)
        active_hold = get_active_hold(date_value, slot["key"])
        held_by_me = bool(active_hold and user and active_hold.user_id == user.id)
        slots.append(
            {
                "key": slot["key"],
                "label": slot["label"],
                "is_full": is_full,
                "is_unavailable": is_unavailable,
                "is_selected": bool(active_hold) and not is_full,
                "held_by_me": held_by_me,
                "hold_expires_at": active_hold.expires_at.isoformat() if active_hold else None,
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
    if "date" in data and "slot" in data and slot_has_started(start_time):
        raise ValueError("This time is no longer available.")

    # Lock resource row while checking availability.
    Resource.objects.select_for_update().get(id=resource.id)
    if has_conflict(resource, start_time, end_time):
        raise ValueError("Reservation time conflicts with another reservation.")

    if "date" in data and "slot" in data:
        active_hold = get_active_hold(data.get("date"), data.get("slot"))
        if not active_hold:
            raise ValueError("Please select this time again.")
        if active_hold.user_id != user.id:
            raise ValueError("This time is currently selected by another user.")

    reservation = Reservation.objects.create(
        user=user,
        resource=resource,
        start_time=start_time,
        end_time=end_time,
        status=Reservation.Status.CONFIRMED,
        note=data.get("note", ""),
    )
    if "date" in data and "slot" in data:
        release_user_hold(user, data.get("date"), data.get("slot"))
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
    data = reservation_to_dict(reservation)
    data["slot"] = get_slot_key_from_times(reservation.start_time, reservation.end_time)
    publish_event(event_name, data)


def get_slot_key_from_times(start_time, end_time):
    local_start = timezone.localtime(start_time)
    local_end = timezone.localtime(end_time)
    start_hour = local_start.hour
    end_hour = 24 if local_end.hour == 0 else local_end.hour

    for slot in RESTAURANT_SLOTS:
        if slot["start_hour"] == start_hour and slot["end_hour"] == end_hour:
            return slot["key"]
    return None
