import json

# 1. Before marshalling (in-memory data structure)
msg = {"rider_id": "John", "request_id": "req_101", "lat": 37.77, "lon": -122.41}
print("BEFORE MARSHALLING (Python Dict):", type(msg), msg)

# 2. After marshalling (wire format)
raw_bytes = json.dumps(msg).encode("utf-8")
print("\nAFTER MARSHALLING (UTF-8 Bytes):", type(raw_bytes), raw_bytes)

# 3. Receiver unmarshalling
restored = json.loads(raw_bytes.decode("utf-8"))
print("\nUNMARSHALLED (Python Dict):", type(restored), restored)