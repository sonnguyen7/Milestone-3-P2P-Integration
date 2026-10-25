import sys
from messaging import publish

if __name__ == "__main__":
    group = sys.argv[1] if len(sys.argv) > 1 else "drivers.local"
    text = " ".join(sys.argv[2:]) or "High demand: please update your location."
    print(publish("group", group, {"notice": text}), flush=True)
