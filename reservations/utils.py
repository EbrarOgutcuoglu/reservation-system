import json

from django.http import JsonResponse


def read_json(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def api_response(data=None, status=200):
    return JsonResponse(data or {}, status=status)


def api_error(message, status=400):
    return JsonResponse({"error": message}, status=status)

