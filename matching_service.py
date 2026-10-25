import datetime
import json
import math
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from messaging import publish
from peer_overlay import call, endpoint, query

SERVICE = "matching-service"
PORT = int(os.environ.get("MATCHING_PORT", "9000"))
PEER_SEEDS = [endpoint(value.strip()) for value in
              os.environ.get("PEER_SEEDS", "127.0.0.1:9301,127.0.0.1:9302,127.0.0.1:9303,127.0.0.1:9304").split(",")
              if value.strip()]
Log_Dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(Log_Dir, exist_ok=True)
# In-memory registries
drivers = {}          # registration metadata for optional location updates
requests_seen = {}    # request_id -> (signature, http_code, response_dict)
def log(service_name, message):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    line = f"[{ts}] [{service_name}] {message}"
    print(line, flush=True)
    with open(os.path.join(Log_Dir, f"{service_name}.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")

def distance(lat1, lon1, lat2, lon2):
    return math.dist((lat1, lon1), (lat2, lon2))

def push_assignment(driver, rider_id, ride_id):
    url = f"http://{driver['host']}:{driver['port']}/assign"
    payload = json.dumps({"ride_id": ride_id, "rider_id": rider_id}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log(SERVICE, f"WARN could not reach driver for assignment: {e}")
        return None
# Web UI Dashboard (Serves http://localhost:9000/)
HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Ride-Matching Architecture Console</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background-color: #0b111e; color: #e2e8f0; padding: 24px; }
    header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 16px; margin-bottom: 24px; }
    h1 { font-size: 1.5rem; font-weight: 700; color: #f8fafc; }
    .badge-hub { background: #064e3b; color: #34d399; padding: 6px 12px; border-radius: 9999px; font-size: 0.8rem; font-weight: 600; }
    .grid { display: grid; grid-template-columns: 1fr 1.3fr; gap: 24px; }
    .card { background: #131d31; border: 1px solid #1e293b; border-radius: 12px; padding: 20px; }
    .card-header { display: flex; justify-content: space-between; margin-bottom: 16px; border-bottom: 1px solid #1e293b; padding-bottom: 8px; }
    .card-header h2 { font-size: 1.1rem; color: #94a3b8; }
    .pattern-tag { font-size: 0.75rem; color: #38bdf8; font-weight: 600; }
    .field { margin-bottom: 14px; }
    label { display: block; font-size: 0.8rem; color: #94a3b8; margin-bottom: 6px; }
    input { width: 100%; background: #0b111e; border: 1px solid #334155; border-radius: 6px; padding: 10px; color: #f8fafc; font-size: 0.9rem; }
    .row { display: flex; gap: 12px; }
    .btn-row { display: flex; gap: 12px; margin-top: 18px; }
    button { flex: 1; padding: 12px; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; transition: 0.2s; font-size: 0.85rem; }
    .btn-primary { background: #2563eb; color: #fff; }
    .btn-primary:hover { background: #1d4ed8; }
    .btn-retry { background: #d97706; color: #fff; }
    .btn-retry:hover { background: #b45309; }
    table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 0.85rem; }
    th, td { text-align: left; padding: 10px; border-bottom: 1px solid #1e293b; }
    th { color: #64748b; font-weight: 600; }
    .status-badge { padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 700; }
    .avail { background: #064e3b; color: #34d399; }
    .busy { background: #7f1d1d; color: #f87171; }
    pre { background: #000; border: 1px solid #1e293b; border-radius: 6px; padding: 12px; font-family: monospace; font-size: 0.8rem; color: #38bdf8; overflow-x: auto; max-height: 180px; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Ride-Matching Architecture Console</h1>
      <p style="color:#64748b; font-size:0.85rem;">Distributed Systems Milestone 3 — Peer Driver Discovery</p>
    </div>
    <span class="badge-hub">SYSTEM ONLINE: PORT 9000</span>
  </header>

  <div class="grid">
    <!-- Rider Request-Reply Client -->
    <div class="card">
      <div class="card-header">
        <h2>Rider Client</h2>
        <span class="pattern-tag">Pattern: Request-Reply (HTTP / TCP)</span>
      </div>
      <div class="field">
        <label>Rider ID</label>
        <input type="text" id="rider_id" value="rider_son">
      </div>
      <div class="field">
        <label>Request ID (Idempotency Key)</label>
        <input type="text" id="request_id" value="">
      </div>
      <div class="row">
        <div class="field" style="flex:1">
          <label>Pickup Latitude</label>
          <input type="text" id="lat" value="37.7749">
        </div>
        <div class="field" style="flex:1">
          <label>Pickup Longitude</label>
          <input type="text" id="lon" value="-122.4194">
        </div>
      </div>
      <div class="btn-row">
        <button class="btn-primary" onclick="sendRequest(false)">1. Send New Request</button>
        <button class="btn-retry" onclick="sendRequest(true)">2. Retry Same (Duplicate)</button>
      </div>

      <div style="margin-top: 20px;">
        <label>Synchronous Server Reply (Unmarshalled)</label>
        <pre id="reply_box">Waiting for user action...</pre>
      </div>
    </div>

    <!-- Active Driver Pool and Storage -->
    <div class="card">
      <div class="card-header">
        <h2>Peer-Discovered Driver Pool</h2>
        <span class="pattern-tag">Pattern: Peer Lookup + Assignments</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Driver</th>
            <th>Port</th>
            <th>Coordinates</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody id="driver_table">
          <tr><td colspan="4" style="text-align:center; color:#64748b;">No live peers discovered yet.</td></tr>
        </tbody>
      </table>

      <div style="margin-top: 20px;">
        <label>Live Peer Discovery Snapshot</label>
        <pre id="storage_box">{}</pre>
      </div>
    </div>
  </div>

  <script>
    let lastRequestId = "";

    function generateReqId() {
      return "req_" + Date.now();
    }
    document.getElementById("request_id").value = generateReqId();

    async function sendRequest(isRetry) {
      if (!isRetry) {
        lastRequestId = generateReqId();
        document.getElementById("request_id").value = lastRequestId;
      }
      const reqId = document.getElementById("request_id").value;
      const payload = {
        rider_id: document.getElementById("rider_id").value,
        request_id: reqId,
        lat: parseFloat(document.getElementById("lat").value),
        lon: parseFloat(document.getElementById("lon").value)
      };

      try {
        const res = await fetch("/ride/request", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        document.getElementById("reply_box").textContent = JSON.stringify(data, null, 2);
        refreshDrivers();
      } catch (err) {
        document.getElementById("reply_box").textContent = "Error: " + err;
      }
    }

    async function refreshDrivers() {
      try {
        const res = await fetch("/drivers");
        const list = await res.json();
        document.getElementById("storage_box").textContent = JSON.stringify(list, null, 2);

        const tbody = document.getElementById("driver_table");
        const keys = Object.keys(list);
        if (keys.length === 0) {
          tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#64748b;">No live peers discovered yet.</td></tr>';
          return;
        }

        tbody.innerHTML = keys.map(did => {
          const d = list[did];
          const badge = d.available 
            ? '<span class="status-badge avail">AVAILABLE</span>' 
            : '<span class="status-badge busy">MATCHED / BUSY</span>';
          return `<tr>
            <td style="font-weight:600;">${did}</td>
            <td>${d.port}</td>
            <td>(${Number(d.lat).toFixed(4)}, ${Number(d.lon).toFixed(4)})</td>
            <td>${badge}</td>
          </tr>`;
        }).join("");
      } catch (e) {}
    }

    setInterval(refreshDrivers, 2000);
    refreshDrivers();
  </script>
</body>
</html>
"""
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass
    
    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length) if length > 0 else b"{}"
        # Wire log proving unmarshalling
        print(f"\n[UNMARSHAL] <--- RAW WIRE BYTES RECEIVED ({len(raw_body)} bytes):\n{raw_body}", flush=True)
        data = json.loads(raw_body.decode("utf-8") or "{}")
        print(f"[UNMARSHAL] <--- UNMARSHALLED PYTHON DICT:\n{data}\n", flush=True)
        return data

    def _respond(self, code, obj):
        # Wire log proving marshalling
        print(f"\n[MARSHAL] ---> NATIVE PYTHON OBJECT TO SEND:\n{obj}", flush=True)
        body = json.dumps(obj).encode("utf-8")
        print(f"[MARSHAL] ---> MARSHALLED WIRE BYTES ({len(body)} bytes):\n{body}\n", flush=True)

        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif self.path == "/drivers":
            try:
                found = query(PEER_SEEDS, trace=False)
                self._respond(200, {d["driver_id"]: d for d in found["resources"]})
            except OSError:
                self._respond(200, {})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/driver/register":
            data = self._read_json()
            drivers[data["driver_id"]] = {
                "host": data["host"],
                "port": data["port"],
                "lat": data["lat"],
                "lon": data["lon"],
                "available": True,
                "peer_host": data.get("peer_host"),
                "peer_port": data.get("peer_port"),
            }
            log(SERVICE, f"driver registered: {data['driver_id']} at ({data['lat']}, {data['lon']})")
            self._respond(200, {"status": "registered"})
        elif self.path == "/driver/location":
            data = self._read_json()
            d = drivers.get(data["driver_id"])
            if d:
                try:
                    call((d["peer_host"], d["peer_port"]),
                         {"op": "UPDATE_LOCATION", "lat": data["lat"], "lon": data["lon"]})
                except (OSError, ValueError, TypeError) as error:
                    log(SERVICE, f"location update could not reach peer {data['driver_id']}: {error}")
                    self._respond(503, {"status": "peer_unavailable"})
                    return
                d["lat"], d["lon"] = data["lat"], data["lon"]
                log(SERVICE, f"location update from {data['driver_id']}: ({data['lat']}, {data['lon']})")
                self._respond(200, {"status": "updated"})
            else:
                self._respond(404, {"status": "unknown driver"})
        elif self.path == "/ride/request":
            data = self._read_json()
            rider_id = data["rider_id"]
            lat = data["lat"]
            lon = data["lon"]
            request_id = data.get("request_id", rider_id)
            signature = (rider_id, lat, lon)
            # Idempotency check
            if request_id in requests_seen:
                saved_signature, code, result = requests_seen[request_id]
                if signature != saved_signature:
                    log(SERVICE, f"CONFLICT: request_id {request_id} reused with different coordinates")
                    self._respond(409, {"status": "request_id_conflict"})
                else:
                    log(SERVICE, f"IDEMPOTENCY: duplicate request {request_id}; returning cached response")
                    self._respond(code, result)
                return
            log(SERVICE, f"ride request from {rider_id} at ({lat}, {lon}) [req_id={request_id}]")
            try:
                found = query(PEER_SEEDS)
            except OSError as error:
                log(SERVICE, f"peer overlay unavailable: {error}")
                self._respond(503, {"status": "peer_overlay_unavailable"})
                return
            log(SERVICE, f"PEER LOOKUP path={'->'.join(found['path'])} "
                         f"resources={[d['driver_id'] for d in found['resources']]}")
            candidates = [(d["driver_id"], d) for d in found["resources"] if d["available"]]
            if not candidates:
                log(SERVICE, f"no available drivers for {rider_id}")
                self._respond(503, {"status": "no_drivers_available"})
                return
            best_id, best = min(candidates, key=lambda kv: distance(lat, lon, kv[1]["lat"], kv[1]["lon"]))
            ride_id = f"ride-{rider_id}-{best_id}"
            log(SERVICE, f"matched {rider_id} -> {best_id} (ride_id={ride_id}); pushing assignment")
            ack = push_assignment(best, rider_id, ride_id)
            if ack is None:
                log(SERVICE, "assignment outcome uncertain; check driver state")
                result = {"status": "assignment_uncertain", "request_id": request_id}
                requests_seen[request_id] = (signature, 502, result)
                self._respond(502, result)
            else:
                log(SERVICE, f"driver {best_id} acknowledged ride {ride_id}")
                result = {
                    "status": "matched",
                    "ride_id": ride_id,
                    "driver_id": best_id,
                    "request_id": request_id,
                    "lookup_path": found["path"],
                }
                requests_seen[request_id] = (signature, 200, result)
                # Publish event to the standalone TCP broker
                try:
                    publish("publish", "ride.assigned", result)
                    log(SERVICE, f"published ride.assigned event to TCP broker for {ride_id}")
                except Exception as error:
                    log(SERVICE, f"event publication failed: {error}")
                self._respond(200, result)

if __name__ == "__main__":
    # Truncate matching-service.log clean on launch
    with open(os.path.join(Log_Dir, f"{SERVICE}.log"), "w", encoding="utf-8") as f:
        pass
    log(SERVICE, f"Starting Matching Service on port {PORT}...")
    log(SERVICE, f"Web UI available at: http://localhost:{PORT}/")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
