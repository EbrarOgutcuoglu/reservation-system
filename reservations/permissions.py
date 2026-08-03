from functools import wraps

from .auth import verify_token
from .utils import api_error


def get_authenticated_user(request):
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return verify_token(auth_header.replace("Bearer ", "", 1))

    token = request.GET.get("token")
    if token:
        return verify_token(token)

    return None


def login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = get_authenticated_user(request)
        if not user:
            return api_error("Authentication token is missing or invalid.", 401)

        request.user = user
        return view_func(request, *args, **kwargs)

    return wrapper


def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            return api_error("Admin permission is required.", 403)
        return view_func(request, *args, **kwargs)

    return wrapper
