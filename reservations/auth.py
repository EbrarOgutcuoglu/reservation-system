import base64
import hashlib
import hmac
import json
import time

from django.conf import settings
from django.contrib.auth import get_user_model


def _b64_encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64_decode(data):
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(user):
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "user_id": user.id,
        "username": user.username,
        "role": get_role(user),
        "exp": int(time.time()) + 60 * 60 * 24,
    }
    header_part = _b64_encode(json.dumps(header).encode("utf-8"))
    payload_part = _b64_encode(json.dumps(payload).encode("utf-8"))
    unsigned = f"{header_part}.{payload_part}"
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        unsigned.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{unsigned}.{_b64_encode(signature)}"


def verify_token(token):
    try:
        header_part, payload_part, signature_part = token.split(".")
        unsigned = f"{header_part}.{payload_part}"
        expected = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            unsigned.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_b64_encode(expected), signature_part):
            return None

        payload = json.loads(_b64_decode(payload_part))
        if payload["exp"] < int(time.time()):
            return None

        return get_user_model().objects.filter(id=payload["user_id"]).first()
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def get_role(user):
    return "ADMIN" if user.is_staff else "USER"

