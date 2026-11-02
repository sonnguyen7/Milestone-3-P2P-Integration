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
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ride-Matching Architecture Console</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: rgba(16, 24, 40, 0.7);
      --card-border: rgba(255, 255, 255, 0.08);
      --surface-hover: rgba(255, 255, 255, 0.04);
      --accent: #3b82f6;
      --accent-glow: rgba(59, 130, 246, 0.25);
      --emerald: #10b981;
      --emerald-glow: rgba(16, 185, 129, 0.2);
      --rose: #f43f5e;
      --amber: #f59e0b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    
    body {
      background-color: var(--bg);
      background-image: 
        radial-gradient(at 0% 0%, rgba(59, 130, 246, 0.12) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.08) 0px, transparent 50%);
      background-attachment: fixed;
      color: var(--text);
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      padding: 32px;
      -webkit-font-smoothing: antialiased;
    }

    .container {
      max-width: 1380px;
      margin: 0 auto;
    }

    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 24px;
      margin-bottom: 28px;
      border-bottom: 1px solid var(--card-border);
    }

    .title-group h1 {
      font-size: 1.6rem;
      font-weight: 800;
      letter-spacing: -0.025em;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .title-group p {
      color: var(--text-muted);
      font-size: 0.9rem;
      margin-top: 4px;
    }

    .badge-hub {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: #6ee7b7;
      padding: 8px 16px;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.05em;
      box-shadow: 0 0 20px var(--emerald-glow);
    }

    .pulse-dot {
      width: 8px;
      height: 8px;
      background: var(--emerald);
      border-radius: 50%;
      box-shadow: 0 0 10px var(--emerald);
      animation: pulse 2s infinite ease-in-out;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.85); }
    }

    .grid {
      display: grid;
      grid-template-columns: 1.05fr 1.35fr;
      gap: 28px;
    }

    .card {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--card-border);
      border-radius: 18px;
      padding: 24px;
      box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.5);
      position: relative;
      overflow: hidden;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--card-border);
    }

    .card-header h2 {
      font-size: 1.15rem;
      font-weight: 700;
      letter-spacing: -0.01em;
      color: #fff;
    }

    .pattern-tag {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      color: #7dd3fc;
      background: rgba(56, 189, 248, 0.08);
      border: 1px solid rgba(56, 189, 248, 0.2);
      padding: 4px 10px;
      border-radius: 6px;
      font-weight: 600;
    }

    .field { margin-bottom: 16px; }

    label {
      display: block;
      font-size: 0.78rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 8px;
    }

    input {
      width: 100%;
      background: rgba(9, 13, 22, 0.7);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 10px;
      padding: 12px 14px;
      color: #fff;
      font-size: 0.92rem;
      font-weight: 500;
      outline: none;
      transition: all 0.2s ease;
    }

    input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-glow);
      background: rgba(9, 13, 22, 0.95);
    }

    .row { display: flex; gap: 14px; }

    .btn-row {
      display: flex;
      gap: 12px;
      margin-top: 22px;
    }

    button {
      flex: 1;
      padding: 13px 18px;
      border: none;
      border-radius: 10px;
      font-weight: 700;
      font-size: 0.85rem;
      letter-spacing: 0.01em;
      cursor: pointer;
      transition: all 0.2s ease;
      display: inline-flex;
      justify-content: center;
      align-items: center;
      gap: 8px;
    }

    .btn-primary {
      background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
      color: #fff;
      box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
    }

    .btn-primary:hover {
      background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
      box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5);
      transform: translateY(-1px);
    }

    .btn-retry {
      background: rgba(245, 158, 11, 0.1);
      border: 1px solid rgba(245, 158, 11, 0.3);
      color: #fbbf24;
    }

    .btn-retry:hover {
      background: rgba(245, 158, 11, 0.18);
      border-color: rgba(245, 158, 11, 0.5);
      transform: translateY(-1px);
    }

    button:active { transform: translateY(0); }

    .table-container {
      border-radius: 12px;
      border: 1px solid var(--card-border);
      overflow: hidden;
      background: rgba(9, 13, 22, 0.4);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88rem;
    }

    th, td {
      text-align: left;
      padding: 13px 16px;
      border-bottom: 1px solid var(--card-border);
    }

    th {
      background: rgba(255, 255, 255, 0.02);
      color: var(--text-dim);
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    tbody tr {
      transition: background 0.15s ease;
    }

    tbody tr:hover {
      background: var(--surface-hover);
    }

    tbody tr:last-child td {
      border-bottom: none;
    }

    .port-tag {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
      color: #cbd5e1;
      background: rgba(255, 255, 255, 0.05);
      padding: 3px 7px;
      border-radius: 5px;
    }

    .coord-tag {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
      color: var(--text-muted);
    }

    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 10px;
      border-radius: 6px;
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.04em;
    }

    .avail {
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.25);
      color: #34d399;
    }

    .busy {
      background: rgba(244, 63, 94, 0.12);
      border: 1px solid rgba(244, 63, 94, 0.25);
      color: #fb7185;
    }

    .badge-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
    }

    .avail .badge-dot { background: #34d399; }
    .busy .badge-dot { background: #fb7185; }

    .terminal-window {
      background: #050811;
      border: 1px solid var(--card-border);
      border-radius: 12px;
      overflow: hidden;
      margin-top: 18px;
      box-shadow: inset 0 2px 8px rgba(0,0,0,0.4);
    }

    .terminal-bar {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 8px 14px;
      background: rgba(255, 255, 255, 0.02);
      border-bottom: 1px solid var(--card-border);
    }

    .term-dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
    }

    pre {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
      line-height: 1.5;
      color: #38bdf8;
      padding: 14px;
      overflow-x: auto;
      max-height: 200px;
      white-space: pre-wrap;
      word-break: break-all;
    }

    @media (max-width: 1024px) {
      .grid { grid-template-columns: 1fr; }
      body { padding: 18px; }
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="title-group">
        <h1>Ride-Matching Architecture Console</h1>
        <p>Distributed Systems Milestone 3 &mdash; Peer-to-Peer Driver Discovery Overlay</p>
      </div>
      <div class="badge-hub">
        <span class="pulse-dot"></span>
        SYSTEM ONLINE &bull; PORT 9000
      </div>
    </header>

    <div class="grid">
      <!-- Rider Request-Reply Client -->
      <div class="card">
        <div class="card-header">
          <h2>Rider Client</h2>
          <span class="pattern-tag">HTTP / TCP Request-Reply</span>
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
          <button class="btn-primary" onclick="sendRequest(false)">
            <span>&rarr;</span> 1. Send New Request
          </button>
          <button class="btn-retry" onclick="sendRequest(true)">
            <span>&#8635;</span> 2. Retry Same (Duplicate)
          </button>
        </div>

        <div style="margin-top: 24px;">
          <label>Synchronous Server Reply (Unmarshalled)</label>
          <div class="terminal-window">
            <div class="terminal-bar">
              <span class="term-dot" style="background:#ff5f56;"></span>
              <span class="term-dot" style="background:#ffbd2e;"></span>
              <span class="term-dot" style="background:#27c93f;"></span>
            </div>
            <pre id="reply_box">Waiting for user action...</pre>
          </div>
        </div>
      </div>

      <!-- Active Driver Pool and Storage -->
      <div class="card">
        <div class="card-header">
          <h2>Peer-Discovered Driver Pool</h2>
          <span class="pattern-tag">Peer Overlay Discovery</span>
        </div>
        
        <div class="table-container">
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
              <tr><td colspan="4" style="text-align:center; color:#64748b; padding:24px;">Scanning overlay for live peers...</td></tr>
            </tbody>
          </table>
        </div>

        <div style="margin-top: 24px;">
          <label>Live Peer Discovery Snapshot</label>
          <div class="terminal-window">
            <div class="terminal-bar">
              <span class="term-dot" style="background:#ff5f56;"></span>
              <span class="term-dot" style="background:#ffbd2e;"></span>
              <span class="term-dot" style="background:#27c93f;"></span>
            </div>
            <pre id="storage_box">{}</pre>
          </div>
        </div>
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
          tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#64748b; padding:24px;">No live peers discovered yet.</td></tr>';
          return;
        }

        tbody.innerHTML = keys.map(did => {
          const d = list[did];
          const badge = d.available 
            ? '<span class="status-badge avail"><span class="badge-dot"></span>AVAILABLE</span>' 
            : '<span class="status-badge busy"><span class="badge-dot"></span>MATCHED / BUSY</span>';
          return `<tr>
            <td style="font-weight:700; color:#fff;">${did}</td>
            <td><span class="port-tag">:${d.port}</span></td>
            <td><span class="coord-tag">(${Number(d.lat).toFixed(4)}, ${Number(d.lon).toFixed(4)})</span></td>
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
