"""Inspect peer membership and route a resource lookup through the overlay."""
import json
import sys
from peer_overlay import call, endpoint, query

def main(args):
    if not args or args[0] not in ("status", "lookup", "scan"):
        raise SystemExit("Usage: py peer_client.py status [host:port] | "
                         "lookup DRIVER_ID [host:port] | scan [host:port]")
    command = args[0]
    if command == "lookup":
        if len(args) < 2:
            raise SystemExit("Usage: py peer_client.py lookup DRIVER_ID [host:port]")
        driver_id = args[1]
        address = endpoint(args[2] if len(args) > 2 else "127.0.0.1:9301")
        result = query([address], kind="find", target_id=driver_id)
    else:
        address = endpoint(args[1] if len(args) > 1 else "127.0.0.1:9301")
        result = (call(address, {"op": "STATUS"}) if command == "status"
                  else query([address], kind="scan"))
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main(sys.argv[1:])
