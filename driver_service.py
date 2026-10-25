import datetime
import json
import os
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
Matching_Host = "localhost"
Matching_Port = int(os.environ.get("MATCHING_PORT", "9000"))
import threading
from messaging import listen
from peer_overlay import PeerNode, endpoint
Log_Dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(Log_Dir, exist_ok=True)

def log(service_name, message):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    line = f"[{ts}] [{service_name}] {message}"
    print(line, flush=True)
    with open(os.path.join(Log_Dir, f"{service_name}.log"), "a") as f:
        f.write(line + "\n")

def post(path, payload):
    url = f"http://{Matching_Host}:{Matching_Port}{path}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3) as resp:
        return json.loads(resp.read())
    
def make_handler(service_name, driver_id, peer_node):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass
        def do_POST(self):
            if self.path == "/assign":
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length))
                if not peer_node.reserve():
                    body = json.dumps({"status": "busy"}).encode()
                    self.send_response(409)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                log(service_name, f"ASSIGNED ride {data['ride_id']} for rider {data['rider_id']}")
                body = json.dumps({"status": "accepted"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()
    return Handler

if __name__ == "__main__":
    driver_id = sys.argv[1] if len (sys.argv) > 1 else "D1"
    my_port = int(sys.argv[2]) if len(sys.argv) > 2 else 9101
    lat = float(sys.argv[3]) if len(sys.argv) > 3 else 37.77
    lon = float(sys.argv[4]) if len(sys.argv) > 4 else -122.41
    service_name = f"driver-{driver_id}"
    log(service_name, f"PID {os.getpid()}; registering with matching service at {Matching_Host}:{Matching_Port}")
    group = sys.argv[5] if len(sys.argv) > 5 else "drivers.local"
    peer_port = int(sys.argv[6]) if len(sys.argv) > 6 else my_port + 200
    bootstrap = endpoint(sys.argv[7]) if len(sys.argv) > 7 else None
    peer_node = PeerNode(driver_id, "127.0.0.1", peer_port, "127.0.0.1",
                         my_port, lat, lon,
                         lambda message: log(service_name + "-peer", message))
    server = HTTPServer(("0.0.0.0", my_port), make_handler(service_name, driver_id, peer_node))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=listen, args=(service_name + "-group", "join", group), daemon=True).start()
    try:
        if bootstrap:
            peer_node.join(bootstrap)
        post("/driver/register", {"driver_id": driver_id, "host": "127.0.0.1",
                                  "port": my_port, "lat": lat, "lon": lon,
                                  "peer_host": "127.0.0.1", "peer_port": peer_port})
        log(service_name, f"registered, assignment port {my_port}, peer port {peer_port}")
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        peer_node.stop(graceful=True)
        server.shutdown()
        server.server_close()
