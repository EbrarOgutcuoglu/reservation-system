import json
import threading
from queue import Empty, Queue

clients = []
clients_lock = threading.Lock()


def add_client():
    client_queue = Queue()
    with clients_lock:
        clients.append(client_queue)
    return client_queue


def remove_client(client_queue):
    with clients_lock:
        if client_queue in clients:
            clients.remove(client_queue)


def publish_event(*args):
    """
    Hem publish_event(message_dict) hem de
    publish_event("hold_created", data) kullanımlarını destekler.
    """
    if len(args) == 1:
        if isinstance(args[0], dict) and "event" in args[0]:
            message = args[0]
        else:
            message = {"event": "message", "data": args[0]}
    elif len(args) >= 2:
        message = {"event": args[0], "data": args[1]}
    else:
        return

    with clients_lock:
        # Bağlı olan tüm istemcilerin kuyruğuna mesajı ekle
        for client_queue in list(clients):
            client_queue.put(message)


def format_sse(message):
    event_name = message.get("event", "message")
    data_content = message.get("data", {})
    return f"event: {event_name}\ndata: {json.dumps(data_content)}\n\n"