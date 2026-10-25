"""Live delivery only: broker acknowledgments count socket sends, not processing."""
import json
import socketserver
import threading
from messaging import PORT, send, log
members = {}
lock = threading.RLock()
class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        key = None
        try:
            raw = self.rfile.readline(65537)
            if len(raw) > 65536:
                raise ValueError("message too large")
            message = json.loads(raw)
            op, target = message["op"], message["target"]
            if not isinstance(target, str) or not target:
                raise ValueError("target must be a nonempty string")
            if op in ("subscribe", "join"):
                key = ("topic" if op == "subscribe" else "group", target)
                with lock:
                    send(self.request, {"status": "ready", "target": target})
                    members.setdefault(key, set()).add(self.request)
                log("broker", f"JOIN {message.get('node')} {key}")
                # Subscribers do not send further commands; EOF removes membership.
                while self.rfile.readline(65537):
                    pass
            elif op in ("publish", "group"):
                key_to_send = ("topic" if op == "publish" else "group", target)
                delivered = 0
                with lock:
                    for sock in list(members.get(key_to_send, set())):
                        try:
                            send(sock, message)
                            delivered += 1
                        except OSError:
                            members[key_to_send].discard(sock)
                send(self.request, {"status": "sent", "recipients": delivered,
                                    "message_id": message["message_id"]})
                log("broker", f"SEND {message} recipients={delivered}")
            else:
                raise ValueError("unknown operation")
        except (ValueError, KeyError, TypeError) as error:
            try:
                send(self.request, {"status": "error", "detail": str(error)})
            except OSError:
                pass
        except OSError:
            pass
        finally:
            if key:
                with lock:
                    members.get(key, set()).discard(self.request)
class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == "__main__":
    with Server(("127.0.0.1", PORT), Handler) as server:
        log("broker", f"listening on TCP port {PORT}")
        server.serve_forever()
