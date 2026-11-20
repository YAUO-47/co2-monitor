"""Seed synthetic history through the same HTTP API used by the device."""
import argparse
import json
import math
import time
from urllib.request import Request, urlopen


def send(base, timestamp):
    # 用两条正弦波合成演示读数，并走与 ESP32 相同的上传接口。
    minute = timestamp / 60
    ppm = 925 + 285 * math.sin(minute / 19) + 30 * math.sin(minute / 4)
    payload = {"device_id": "demo", "sampled_at": timestamp, "co2_ppm": round(ppm, 1)}
    request = Request(base.rstrip("/") + "/readings", json.dumps(payload).encode(),
                      {"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        return response.status


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--seed", action="store_true", help="Upload six hours of synthetic history")
    parser.add_argument("--once", action="store_true", help="Exit after a single live sample")
    args = parser.parse_args()
    if args.seed:
        now = int(time.time())
        for timestamp in range(now // 60 * 60 - 6 * 3600 + 5, now, 60):
            send(args.url, timestamp)
        print("Uploaded synthetic history.", flush=True)
    try:
        while True:
            print("Demo reading HTTP", send(args.url, int(time.time())), flush=True)
            if args.once:
                break
            time.sleep(10)
    except KeyboardInterrupt:
        pass
