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


def publish_event(event_name, data):
    message = {
        "event": event_name,
        "data": data,
    }
    with clients_lock:
        current_clients = list(clients)

    for client_queue in current_clients:
        client_queue.put(message)


def format_sse(message):
    return (
        f"event: {message['event']}\n"
        f"data: {json.dumps(message['data'])}\n\n"
    )
