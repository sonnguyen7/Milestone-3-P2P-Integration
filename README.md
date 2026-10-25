# CECS 327 - Distributed Ride-Matching System

**Milestone 3: Peer-to-Peer Overlay Network & Driver Discovery**

This milestone implements a distributed, successor-routed TCP peer-to-peer ring overlay connecting driver nodes (D1–D4). The centralized matching coordinator discovers available drivers dynamically by routing lookup queries through the peer ring rather than querying a static local registry. Request-reply HTTP interactions, JSON marshalling, pub-sub event notifications, and multicast group alerts from Milestone 2 remain fully integrated.

## 1. Required Software

* **Python 3.10+** (Tested on Python 3.14+)

* **Visual Studio Code** (or any code editor / terminal emulator)

* **PowerShell** (Windows) or **Terminal** (macOS/Linux)

## 2. How to Install Dependencies

* **Standard Library Only:** This system runs entirely on Python's built-in modules (`http.server`, `socket`, `socketserver`, `threading`, `json`, `math`, `urllib`).

* **No external packages required:** There is no `pip install` step.

## 3. How to Start Each Service

Open separate VS Code terminal tabs inside the project folder (`Milestone-3-Distributed-Ride-Matching-main`). Execute commands in the following order:

| Terminal | Process / Node | Command (Windows: `py`, macOS/Linux: `python3`) | Role & Network Port | 
| ----- | ----- | ----- | ----- | 
| **1** | Event Broker | `py event_broker.py` | TCP Pub-Sub & Group Broker (Port `9200`) | 
| **2** | Matching Service | `py matching_service.py` | HTTP Gateway & Web UI (Port `9000`) | 
| **3** | Audit Subscriber | `py subscriber.py audit` | Pub-Sub listener on `ride.assigned` | 
| **4** | Monitor Subscriber | `py subscriber.py monitor` | Pub-Sub listener on `ride.assigned` | 
| **5** | Driver D1 (Peer Seed) | `py driver_service.py D1 9101 37.770 -122.410 drivers.local 9301` | Bootstrap node; initializes ring (Peer Port `9301`) | 
| **6** | Driver D2 (Peer Node) | `py driver_service.py D2 9102 37.790 -122.420 drivers.local 9302 127.0.0.1:9301` | Joins ring via D1 (Peer Port `9302`) | 
| **7** | Driver D3 (Peer Node) | `py` driver_service.py D3` 9103 37.760 -122.400 drivers.local 9303 127.0.0.1:9301` | Joins ring via D1 (Peer Port `9303`) | 
| **8** | Driver D4 (Dynamic Join) | *Started during demo step 2* | 4th peer node; proves dynamic join (Peer Port `9304`) | 
| **9** | Interactive Runner | *Terminal for running client inspection queries* | Inspection CLI & Test Runner | 

*Note: Clean previous logs before launching by running `py clean_logs.py` in Terminal 9.*

## 4. How to Run the Demo

### Step 1: Verify Initial 3-Node Ring

In Terminal 9, inspect the active membership before D4 joins:

```
py peer_client.py status 127.0.0.1:9301

```

*Expected Output:* `members: ["D1", "D2", "D3"]` and `neighbors: ["D3", "D2"]`.

### Step 2: Demonstrate Dynamic Peer Join (Driver D4)

Start Terminal 8 to join the 4th peer to the overlay:

```
py driver_service.py D4 9104 37.780 -122.430 drivers.local 9304 127.0.0.1:9301

```

Re-run `py peer_client.py status 127.0.0.1:9301` in Terminal 9. *Expected Output:* Membership updates dynamically to 4 nodes: `["D1", "D2", "D3", "D4"]`.

### Step 3: Demonstrate Multi-Hop Overlay Routing & Discovery

In Terminal 9, execute a full overlay scan:

```
py peer_client.py scan 127.0.0.1:9301

```

*Expected Output:* Output displays `"status": "complete"`, `"path":` \["D1", "D2", "D3",` "D4"]`, and aggregates availability resources from all 4 peers.

Run a targeted resource lookup:

```
py peer_client.py lookup D3 127.0.0.1:9301

```

*Expected Output:* Query hops clockwise along `["D1", "D2", "D3"]` and terminates with `"status": "found"`.

### Step 4: Web Console & Application Integration

1. Open a browser to `http://localhost:9000/`.

2. Notice the **Peer-Discovered Driver Pool** table showing all 4 live drivers fetched via peer discovery queries.

3. Click **1. Send New Request**.

4. The server returns an HTTP 200 JSON payload containing `"lookup_path": ["D1", "D2", "D3", "D4"]` and assigns closest driver D1.

5. Terminals 3 and 4 print the asynchronous `ride.assigned` pub-sub notification.

## 5. How to Reproduce the Test Cases

### Test Case 1: Graceful Peer Leave (Driver D4)

1. Go to **Terminal 8** (Driver D4) and press **Ctrl + C**.

2. Driver D4 executes `peer_node.stop(graceful=True)`, multicasts `LEAVE D4` to its neighbors, and shuts down cleanly.

3. In Terminal 9, run:

   ```
   py peer_client.py status 127.0.0.1:9301
   
   ```

4. **Expected Output:** Membership cleanly reduces to `["D1", "D2", "D3"]` and neighbor pointers reconnect (`neighbors: ["D3", "D2"]`).

### Test Case 2: Abrupt Peer Crash & Automatic Ring Repair (Driver D3)

1. Go to **Terminal 7** (Driver D3) and click the **trash can icon** in VS Code (or run `Stop-Process -Id <D3_PID> -Force` in PowerShell) to simulate a sudden, ungraceful crash without a `LEAVE` packet.

2. In Terminal 9, issue an overlay scan:

   ```
   py peer_client.py scan 127.0.0.1:9301
   
   ```

3. **Expected Output:** Driver D2 attempts to forward over TCP to D3, catches an `OSError`, logs `FAIL D3 unreachable`, issues an automatic `REMOVE D3` alert, and completes the scan across surviving nodes (`path: ["D1", "D2"]`). Running `py peer_client.py status` confirms ring convergence to 2 nodes.

### Test Case 3: Match Allocation After Failure

1. In Terminal 9, run:

   ```
   py rider_client.py Emma 37.760 -122.400 req-emma
   
   ```

2. **Expected Output:** The matching service discovers surviving nodes through the repaired ring and matches Emma to D2 without hanging.

### Test Case 4: Multicast Group Driver Communication

1. In Terminal 9, broadcast an administrative alert:

   ```
   py group_client.py drivers.local "High demand in your area"
   
   ```

2. **Expected Output:** Returns `recipients: 2` (matching active surviving drivers D1 and D2), and both terminals log the notice simultaneously.

### Test Case 5: Wire Marshalling Verification

1. In Terminal 9, run:

   ```
   py demo_marshall.py
   
   ```

2. **Expected Output:** Displays in-memory Python dictionary, UTF-8 raw wire bytes, and unmarshalled receiver dictionary.

## 6. Architecture & Network Topology

```
flowchart TD
    D1["Driver D1 (Peer: 9301 | HTTP: 9101)"] -->|TCP Hop| D2["Driver D2 (Peer: 9302 | HTTP: 9102)"]
    D2 -->|TCP Hop| D3["Driver D3 (Peer: 9303 | HTTP: 9103)"]
    D3 -->|TCP Hop| D4["Driver D4 (Peer: 9304 | HTTP: 9104)"]
    D4 -->|TCP Hop| D1
    
    MS["Matching Service (:9000)"] -.->|Peer Query / LOOKUP| D1
    MS ==>|HTTP POST /assign| D1
    MS -->|Publish ride.assigned| EB["Event Broker (:9200)"]
    EB -->|TCP Notification| Sub1["Audit Subscriber"]
    EB -->|TCP Notification| Sub2["Monitor Subscriber"]

```

* **Overlay Topology:** Clockwise successor-routed TCP ring ordered by driver ID (`D1 -> D2 -> D3 -> D4 -> D1`).

* **Framing Protocol:** Newline-delimited UTF-8 JSON payloads over raw TCP sockets.

* **Failure Model:** Fail-stop detection with 3-second socket timeouts, dynamic removal propagation, and ring repair.

## 7. Files and Port Allocations

| File | Role | 
| ----- | ----- | 
| `peer_overlay.py` | Core P2P ring engine, membership state, neighbor links, multi-hop routing | 
| `peer_client.py` | Command-line tool for querying ring `status`, `lookup <driver>`, or `scan` | 
| `driver_service.py` | Driver node runner: runs assignment HTTP server, `PeerNode`, and broker listener | 
| `matching_service.py` | Central matching coordinator & web dashboard; queries peer ring for discovery | 
| `rider_client.py` | CLI rider client sending synchronous HTTP ride requests | 
| `event_broker.py` | Standalone TCP broker managing topics (`ride.assigned`) and groups (`drivers.local`) | 
| `subscriber.py` | Pub | 
