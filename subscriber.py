import sys
from messaging import listen

if __name__ == "__main__":
    listen(sys.argv[1] if len(sys.argv) > 1 else "monitor", "subscribe", "ride.assigned")
