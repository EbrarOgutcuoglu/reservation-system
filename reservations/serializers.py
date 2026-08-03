from django.utils import timezone

from .auth import get_role


def user_to_dict(user):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": get_role(user),
    }


def resource_to_dict(resource):
    return {
        "id": resource.id,
        "name": resource.name,
        "description": resource.description,
        "is_active": resource.is_active,
    }


def reservation_to_dict(reservation):
    start_time = timezone.localtime(reservation.start_time)
    end_time = timezone.localtime(reservation.end_time)
    return {
        "id": reservation.id,
        "user": user_to_dict(reservation.user),
        "resource": resource_to_dict(reservation.resource),
        "start_time": reservation.start_time.isoformat(),
        "end_time": reservation.end_time.isoformat(),
        "date": start_time.date().isoformat(),
        "time_range": f"{start_time:%H:%M} - {end_time:%H:%M}",
        "status": reservation.status,
        "note": reservation.note,
        "created_at": reservation.created_at.isoformat(),
        "updated_at": reservation.updated_at.isoformat(),
    }
