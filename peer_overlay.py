"""Small successor-routed peer overlay for discovering live driver services.
Peers know membership addresses, but only the owner knows its current driver
availability. A lookup visits peers over TCP, rather than querying the old
matching-service registration table. JSON messages are newline framed.
"""
import json
import socket
import socketserver
import threading
import uuid
MAX_MESSAGE = 65536

def endpoint(value):
    host, separator, port = value.rpartition(":")
    if not separator or not host or not port.isdigit():
        raise ValueError("expected host:port")
    return host, int(port)

def call(address, message, timeout=1.5):
    with socket.create_connection(address, timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall((json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8"))
        raw = sock.makefile("rb").readline(MAX_MESSAGE + 1)
    if not raw or len(raw) > MAX_MESSAGE:
        raise OSError("missing or oversized peer reply")
    reply = json.loads(raw)
    if reply.get("status") == "error":
        raise ValueError(reply.get("detail", "peer error"))
    return reply

def query(seeds, kind="scan", target_id=None, trace=True):
    """Try known entry points; routing and discovery happen inside the overlay."""
    message = {"op": "LOOKUP", "kind": kind, "target_id": target_id,
               "query_id": uuid.uuid4().hex, "path": [], "ttl": 32, "trace": trace}
    last_error = None
    for seed in seeds:
        try:
            return call(seed, message, timeout=4)
        except (OSError, ValueError) as error:
            last_error = error
    raise OSError(f"no reachable peer entry point: {last_error}")

class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            raw = self.rfile.readline(MAX_MESSAGE + 1)
            if not raw or len(raw) > MAX_MESSAGE:
                raise ValueError("empty or oversized message")
            response = self.server.node.handle_message(json.loads(raw))
        except (ValueError, KeyError, TypeError) as error:
            response = {"status": "error", "detail": str(error)}
        self.wfile.write((json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8"))

class PeerNode:
    def __init__(self, driver_id, peer_host, peer_port, http_host, http_port,
                 lat, lon, log):
        self.driver_id = driver_id
        self.address = (peer_host, peer_port)
        self.resource = {"driver_id": driver_id, "host": http_host,
                         "port": http_port, "lat": lat, "lon": lon,
                         "available": True}
        self.identity = {"id": driver_id, "host": peer_host, "port": peer_port,
                         "incarnation": uuid.uuid4().hex}
        self.members = {driver_id: self.identity}
        self.lock = threading.RLock()
        self.log = log
        self.server = _Server(self.address, _Handler)
        self.server.node = self
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.log(f"START {driver_id} peer={peer_host}:{peer_port}")

    def join(self, bootstrap):
        reply = call(bootstrap, {"op": "JOIN", "peer": self.identity})
        self._merge(reply["members"])
        # Announce to every known member. Data lookups still use overlay hops.
        for peer in self._others():
            try:
                call((peer["host"], peer["port"]),
                     {"op": "ANNOUNCE", "peer": self.identity})
            except OSError:
                self._remove(peer["id"], peer["incarnation"])
        self.log(f"JOIN membership={self.member_ids()} neighbors={self.neighbors()}")

    def stop(self, graceful=True):
        if graceful:
            for peer in self._others():
                try:
                    call((peer["host"], peer["port"]),
                         {"op": "LEAVE", "peer": self.identity}, timeout=0.5)
                except OSError:
                    pass
            self.log(f"LEAVE {self.driver_id}")
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def reserve(self):
        with self.lock:
            if not self.resource["available"]:
                return False
            self.resource["available"] = False
            return True

    def update_location(self, lat, lon):
        with self.lock:
            self.resource["lat"] = float(lat)
            self.resource["lon"] = float(lon)

    def member_ids(self):
        with self.lock:
            return sorted(self.members)

    def neighbors(self):
        ids = self.member_ids()
        if len(ids) < 2:
            return []
        pos = ids.index(self.driver_id)
        return list(dict.fromkeys((ids[(pos - 1) % len(ids)],
                                   ids[(pos + 1) % len(ids)])))

    def _others(self):
        with self.lock:
            return [dict(peer) for key, peer in self.members.items()
                    if key != self.driver_id]

    def _merge(self, peers):
        with self.lock:
            for peer in peers:
                if peer["id"] != self.driver_id:
                    self.members[peer["id"]] = peer

    def _remove(self, driver_id, incarnation):
        with self.lock:
            old = self.members.get(driver_id)
            if old and old.get("incarnation") == incarnation and driver_id != self.driver_id:
                del self.members[driver_id]
                return True
        return False

    def _failed(self, peer):
        if self._remove(peer["id"], peer["incarnation"]):
            self.log(f"FAIL {peer['id']} unreachable; neighbors={self.neighbors()}")
            for other in self._others():
                try:
                    call((other["host"], other["port"]),
                         {"op": "REMOVE", "peer": peer}, timeout=0.5)
                except OSError:
                    pass

    def _next(self, path):
        with self.lock:
            ids = sorted(self.members)
            pos = ids.index(self.driver_id)
            for offset in range(1, len(ids)):
                peer_id = ids[(pos + offset) % len(ids)]
                if peer_id not in path:
                    return dict(self.members[peer_id])
        return None

    def handle_message(self, message):
        op = message["op"]
        if op == "JOIN":
            peer = message["peer"]
            self._merge([peer])
            self.log(f"JOIN {peer['id']} neighbors={self.neighbors()}")
            with self.lock:
                return {"status": "ok", "members": list(self.members.values())}
        if op == "ANNOUNCE":
            self._merge([message["peer"]])
            self.log(f"ANNOUNCE {message['peer']['id']} neighbors={self.neighbors()}")
            return {"status": "ok"}
        if op in ("LEAVE", "REMOVE"):
            peer = message["peer"]
            if self._remove(peer["id"], peer["incarnation"]):
                self.log(f"{op} {peer['id']} neighbors={self.neighbors()}")
            return {"status": "ok"}
        if op == "STATUS":
            with self.lock:
                return {"status": "ok", "peer": self.identity,
                        "members": sorted(self.members),
                        "neighbors": self.neighbors(),
                        "resource": dict(self.resource)}
        if op == "UPDATE_LOCATION":
            self.update_location(message["lat"], message["lon"])
            self.log(f"LOCATION {self.driver_id} ({message['lat']}, {message['lon']})")
            return {"status": "updated"}
        if op == "LOOKUP":
            return self._lookup(message)
        raise ValueError(f"unknown operation: {op}")

    def _lookup(self, message):
        kind = message["kind"]
        if kind not in ("scan", "find"):
            raise ValueError("lookup kind must be scan or find")
        path = list(message.get("path", []))
        if self.driver_id in path:
            raise ValueError("lookup loop detected")
        path.append(self.driver_id)
        trace = bool(message.get("trace", False))
        query_id = message.get("query_id", "unknown")
        if trace:
            self.log(f"LOOKUP {query_id} kind={kind} target={message.get('target_id')} path={'->'.join(path)}")
        with self.lock:
            own = dict(self.resource)
        resources = ([own] if kind == "scan" or message.get("target_id") == self.driver_id
                     else [])
        if kind == "find" and resources:
            if trace:
                self.log(f"FOUND {query_id} resource={self.driver_id} path={'->'.join(path)}")
            return {"status": "found", "path": path, "resources": resources,
                    "query_id": query_id}
        remaining = int(message.get("ttl", 0))
        while remaining > 0:
            peer = self._next(path)
            if peer is None:
                break
            if trace:
                self.log(f"FORWARD {query_id} {self.driver_id}->{peer['id']}")
            outgoing = dict(message, path=path, ttl=remaining - 1)
            try:
                reply = call((peer["host"], peer["port"]), outgoing, timeout=3)
                return {"status": reply["status"], "path": reply["path"],
                        "resources": resources + reply["resources"],
                        "query_id": query_id}
            except OSError:
                self._failed(peer)
                remaining -= 1
        return {"status": "complete" if kind == "scan" else "missing",
                "path": path, "resources": resources, "query_id": query_id}
