import asyncio
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


def add_async_client():
    client_queue = asyncio.Queue()
    client = {
        "loop": asyncio.get_running_loop(),
        "queue": client_queue,
    }
    with clients_lock:
        clients.append(client)
    return client


def remove_client(client_queue):
    with clients_lock:
        if client_queue in clients:
            clients.remove(client_queue)


def publish_event(*args):
    # Eğer 2 parametre geldiyse (event_type, data) birleştir, tek geldiyse olduğu gibi al
    if len(args) == 1:
        message = args[0]
    else:
        message = {"event": args[0], "data": args[1]}

    dead_clients = []
    for client in clients:
        loop = client.get("loop")
        if loop and not loop.is_closed() and loop.is_running():
            try:
                loop.call_soon_threadsafe(client["queue"].put_nowait, message)
            except RuntimeError:
                dead_clients.append(client)
        else:
            dead_clients.append(client)

    for dead in dead_clients:
        if dead in clients:
            clients.remove(dead)


def format_sse(message):
    return (
        f"event: {message['event']}\n"
        f"data: {json.dumps(message['data'])}\n\n"
    )
