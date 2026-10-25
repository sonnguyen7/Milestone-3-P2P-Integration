"""Newline-framed JSON over TCP: topics and named driver groups."""
import datetime
import json
import os
import socket
import time
import uuid
HOST = "127.0.0.1"
PORT = int(os.environ.get("BROKER_PORT", "9200"))

def log(name, message):
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
    line = f"[{stamp}] [{name}] {message}"
    print(line, flush=True)
    folder = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name + ".log"), "a", encoding="utf-8") as file:
        file.write(line + "\n")

def send(sock, message):
    sock.sendall((json.dumps(message) + "\n").encode("utf-8"))

def envelope(kind, target, payload):
    return {"op": kind, "target": target, "message_id": str(uuid.uuid4()),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "payload": payload}

def publish(kind, target, payload):
    message = envelope(kind, target, payload)
    with socket.create_connection((HOST, PORT), timeout=3) as sock:
        send(sock, message)
        reply = json.loads(sock.makefile("rb").readline())
    log("publisher", f"SEND {message} ACK {reply}")
    if reply.get("status") != "sent":
        raise RuntimeError(reply)
    return reply

def listen(name, kind, target):
    while True:
        try:
            with socket.create_connection((HOST, PORT), timeout=3) as sock:
                sock.settimeout(None)
                send(sock, {"op": kind, "target": target, "node": name})
                for line in sock.makefile("rb"):
                    log(name, f"RECEIVE {json.loads(line)}")
            log(name, "broker disconnected; reconnecting")
        except (OSError, ValueError) as error:
            log(name, f"broker unavailable: {error}; reconnecting")
        time.sleep(1)
