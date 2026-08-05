import asyncio
import logging

from asgiref.sync import sync_to_async
from django.contrib.auth import authenticate, get_user_model
from django.http import StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from .auth import create_token
from .events import add_async_client, format_sse, remove_client
from .models import Reservation, Resource
from .permissions import admin_required, get_authenticated_user, login_required
from .serializers import reservation_to_dict, resource_to_dict, user_to_dict
from .services import (
    cancel_reservation,
    change_reservation_status,
    create_reservation,
    get_restaurant_availability,
    hold_slot,
    release_user_hold,
    update_reservation,
)
from .utils import api_error, api_response, read_json

logger = logging.getLogger(__name__)
User = get_user_model()


def home(request):
    return render(request, "dashboard.html")


def login_page(request):
    return render(request, "login.html")


def register_page(request):
    return render(request, "register.html")


def reservations_page(request):
    return render(request, "reservations.html")


def new_reservation_page(request):
    return render(request, "new_reservation.html")


def events_page(request):
    return render(request, "events.html")


def manager_page(request):
    return render(request, "manager.html")


def api_home(request):
    if request.method != "GET":
        return api_error("Method is not allowed.", 405)

    return api_response(
        {
            "message": "Reservation API is running.",
            "public_endpoints": [
                "POST /api/auth/register/",
                "POST /api/auth/login/",
            ],
            "protected_endpoints": [
                "GET /api/profile/",
                "GET /api/resources/",
                "GET /api/reservations/",
                "POST /api/reservations/",
                "GET /api/events/?token=<JWT_TOKEN>",
            ],
        }
    )


@csrf_exempt
def register(request):
    if request.method != "POST":
        return api_error("Method is not allowed.", 405)

    data = read_json(request)
    username = data.get("username", "").strip()
    password = data.get("password", "")
    email = data.get("email", "").strip()

    if not username or not password:
        return api_error("username and password are required.")
    if User.objects.filter(username=username).exists():
        return api_error("Username is already used.")

    user = User.objects.create_user(username=username, password=password, email=email)
    logger.info("New user registered: %s", username)
    return api_response({"user": user_to_dict(user), "token": create_token(user)}, 201)


@csrf_exempt
def login(request):
    if request.method != "POST":
        return api_error("Method is not allowed.", 405)

    data = read_json(request)
    user = authenticate(username=data.get("username"), password=data.get("password"))
    if not user:
        return api_error("Invalid username or password.", 401)

    logger.info("User logged in: %s", user.username)
    return api_response({"user": user_to_dict(user), "token": create_token(user)})


@login_required
def profile(request):
    if request.method != "GET":
        return api_error("Method is not allowed.", 405)
    return api_response({"user": user_to_dict(request.user)})


@login_required
def resource_list(request):
    if request.method != "GET":
        return api_error("Method is not allowed.", 405)

    resources = Resource.objects.filter(is_active=True)
    return api_response({"resources": [resource_to_dict(item) for item in resources]})


@login_required
def availability(request):
    if request.method != "GET":
        return api_error("Method is not allowed.", 405)

    date_value = request.GET.get("date")
    try:
        return api_response({"slots": get_restaurant_availability(date_value, request.user)})
    except ValueError as exc:
        return api_error(str(exc))


@csrf_exempt
@login_required
def hold_reservation_slot(request):
    if request.method != "POST":
        return api_error("Method is not allowed.", 405)

    data = read_json(request)
    try:
        hold = hold_slot(request.user, data.get("date"), data.get("slot"))
        return api_response(
            {
                "hold": {
                    "date": hold.date.isoformat(),
                    "slot": hold.slot,
                    "expires_at": hold.expires_at.isoformat(),
                }
            },
            201,
        )
    except ValueError as exc:
        return api_error(str(exc))


@csrf_exempt
@login_required
def release_reservation_hold(request):
    if request.method != "POST":
        return api_error("Method is not allowed.", 405)

    data = read_json(request)
    release_user_hold(request.user, data.get("date"), data.get("slot"))
    return api_response({"message": "Hold released."})


@csrf_exempt
@login_required
def reservation_list_create(request):
    if request.method == "GET":
        reservations = Reservation.objects.filter(user=request.user).select_related("user", "resource")
        return api_response({"reservations": [reservation_to_dict(item) for item in reservations]})

    if request.method == "POST":
        try:
            reservation = create_reservation(request.user, read_json(request))
            return api_response({"reservation": reservation_to_dict(reservation)}, 201)
        except ValueError as exc:
            logger.warning("Reservation create failed: %s", exc)
            return api_error(str(exc))

    return api_error("Method is not allowed.", 405)


@csrf_exempt
@login_required
def reservation_detail(request, reservation_id):
    reservation = Reservation.objects.filter(
        id=reservation_id,
        user=request.user,
    ).select_related("user", "resource").first()
    if not reservation:
        return api_error("Reservation was not found.", 404)

    if request.method == "GET":
        return api_response({"reservation": reservation_to_dict(reservation)})

    if request.method in ["PUT", "PATCH"]:
        try:
            reservation = update_reservation(reservation, read_json(request))
            return api_response({"reservation": reservation_to_dict(reservation)})
        except ValueError as exc:
            logger.warning("Reservation update failed: %s", exc)
            return api_error(str(exc))

    if request.method == "DELETE":
        reservation = cancel_reservation(reservation)
        return api_response({"reservation": reservation_to_dict(reservation)})

    return api_error("Method is not allowed.", 405)


@admin_required
def admin_reservations(request):
    if request.method != "GET":
        return api_error("Method is not allowed.", 405)

    reservations = Reservation.objects.select_related("user", "resource").all()
    return api_response({"reservations": [reservation_to_dict(item) for item in reservations]})


@csrf_exempt
@admin_required
def admin_change_status(request, reservation_id):
    if request.method not in ["PUT", "PATCH"]:
        return api_error("Method is not allowed.", 405)

    reservation = Reservation.objects.filter(id=reservation_id).select_related("user", "resource").first()
    if not reservation:
        return api_error("Reservation was not found.", 404)

    try:
        reservation = change_reservation_status(reservation, read_json(request).get("status"))
        return api_response({"reservation": reservation_to_dict(reservation)})
    except ValueError as exc:
        logger.warning("Status change failed: %s", exc)
        return api_error(str(exc))


@admin_required
def admin_users(request):
    if request.method != "GET":
        return api_error("Method is not allowed.", 405)

    users = User.objects.all().order_by("id")
    return api_response({"users": [user_to_dict(user) for user in users]})


async def event_stream(request):
    if request.method != "GET":
        return api_error("Method is not allowed.", 405)

    user = await sync_to_async(get_authenticated_user)(request)
    if not user:
        return api_error("Authentication token is missing or invalid.", 401)

    request.user = user
    client = add_async_client()
    client_queue = client["queue"]

    async def stream():
        try:
            yield "event: connected\ndata: {\"message\": \"SSE connected\"}\n\n"
            while True:
                try:
                    message = await asyncio.wait_for(client_queue.get(), timeout=15)
                    yield format_sse(message)
                except asyncio.TimeoutError:
                    # Keep connection alive for browsers.
                    yield ": heartbeat\n\n"
        finally:
            remove_client(client)

    response = StreamingHttpResponse(stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
