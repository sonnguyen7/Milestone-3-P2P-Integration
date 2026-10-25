import datetime
import json
import os
import sys
import urllib.request
Matching_Host = "localhost"
Matching_Port = int(os.environ.get("MATCHING_PORT", "9000"))
Log_Dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(Log_Dir, exist_ok=True)

def log(service_name, message):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    line = f"[{ts}] [{service_name}] {message}"
    print(line, flush=True)
    with open(os.path.join(Log_Dir, f"{service_name}.log"), "a") as f:
        f.write(line + "\n")

if __name__ == "__main__":
    rider_id = sys.argv[1] if len(sys.argv) > 1 else "R1"
    lat = float(sys.argv[2]) if len(sys.argv) > 2 else 37.775
    lon = float(sys.argv[3]) if len(sys.argv) > 3 else -122.415
    service_name = f"rider-{rider_id}"
    url = f"http://{Matching_Host}:{Matching_Port}/ride/request"
    request_id = sys.argv[4] if len(sys.argv) > 4 else rider_id
    payload = json.dumps({"rider_id": rider_id, "lat": lat,"lon": lon, "request_id": request_id}).encode()
    req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json"})
    log(service_name, f"requesting ride at ({lat}, {lon})")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            log(service_name, f"response: {result}")
    except urllib.error.HTTPError as e:
        log(service_name, f"request failed: HTTP {e.code} {e.read().decode()}")
    except Exception as e:
        log(service_name, f"request failed: {e}")