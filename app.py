"""Local CO₂ monitor and device API."""
import argparse
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "readings.sqlite3"
DEVICE = re.compile(r"[A-Za-z0-9_-]{1,48}")


def connect():
    return sqlite3.connect(DATABASE)


def initialize():
    with closing(connect()) as db, db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                device TEXT, sampled INTEGER, received INTEGER, ppm REAL,
                PRIMARY KEY (device, sampled)
            )
        """)

        # 为已有数据库补列，旧采样保留，缺失的温湿度用 NULL 表示。
        columns = {row[1] for row in db.execute("PRAGMA table_info(readings)")}
        for name in ("temperature_c", "humidity_pct"):
            if name not in columns:
                db.execute(f"ALTER TABLE readings ADD COLUMN {name} REAL")


def readings(device, since, include_environment=False):
    columns = "sampled, ppm, temperature_c, humidity_pct" if include_environment else "sampled, ppm"
    with closing(connect()) as db:
        return db.execute(
            f"SELECT {columns} FROM readings WHERE device=? AND sampled>=? ORDER BY sampled",
            (device, since),
        ).fetchall()


class Handler(BaseHTTPRequestHandler):
    def send_data(self, status, data, content_type="application/json"):
        body = json.dumps(data).encode() if content_type == "application/json" else data
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/readings":
            return self.send_data(404, {"error": "Unknown endpoint"})
        now = int(time.time())
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096:
                raise ValueError
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError
            device = payload["device_id"]
            sampled = payload["sampled_at"]
            ppm = payload["co2_ppm"]
            temperature = payload.get("temperature_c")
            humidity = payload.get("humidity_pct")
            # 字段可缺省，兼容只上传 CO₂ 的旧固件。
            for value, lower, upper in ((temperature, -45, 130), (humidity, 0, 100)):
                if value is not None and (
                    type(value) not in (float, int) or not math.isfinite(value)
                    or not lower <= value <= upper
                ):
                    raise ValueError
            if (not DEVICE.fullmatch(device) or type(sampled) is not int
                    or not 946684800 <= sampled <= now + 5
                    or type(ppm) not in (float, int) or not math.isfinite(ppm) or not 0 < ppm <= 40000):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self.send_data(400, {"error": "Invalid reading"})
        # 同一设备在同一秒的采样只保存一次，重试可安全重复提交。
        with closing(connect()) as db, db:
            inserted = db.execute(
                """INSERT OR IGNORE INTO readings
                   (device, sampled, received, ppm, temperature_c, humidity_pct)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (device, sampled, now, ppm, temperature, humidity),
            ).rowcount
        self.send_data(201 if inserted else 200, {"inserted": bool(inserted)})

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/":
            return self.send_data(200, (ROOT / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
        if url.path != "/readings":
            return self.send_data(404, {"error": "Unknown endpoint"})
        device = parse_qs(url.query).get("device_id", ["demo"])[0]
        if not DEVICE.fullmatch(device):
            return self.send_data(400, {"error": "Invalid device ID"})
        now = int(time.time())
        measurements = readings(device, now - 3600, include_environment=True)
        # 保留原有 rows 接口，训练程序和现有调用者仍读取时间与 CO₂ 两列。
        rows = [row[:2] for row in measurements]
        # 用采样时间判断新鲜度，避免延迟上传的旧数据被当成实时读数。
        stale = not rows or now - rows[-1][0] > 30
        forecast = None
        model_path = ROOT / "models" / (device + ".json")
        if not stale and model_path.exists():
            from train import features, minute_means
            # 只使用已结束的分钟，让实时预测和训练采用同样的特征。
            series = minute_means(rows, before=now // 60)
            inputs = features(series, now // 60 - 1)
            if inputs is not None:
                current, change = inputs
                model = json.loads(model_path.read_text())
                ppm = max(0, current + model["intercept"] + model["slope"] * change)
                if math.isfinite(ppm):
                    forecast = {"ppm": round(ppm, 1), "at": (now // 60 + 10) * 60}
        self.send_data(200, {"rows": rows, "stale": stale, "forecast": forecast,
                                  "environment": [
                                      {"sampled_at": row[0], "temperature_c": row[2],
                                       "humidity_pct": row[3]} for row in measurements
                                  ]})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    initialize()
    with ThreadingHTTPServer((args.host, args.port), Handler) as server:
        print(f"CO₂ monitor listening on {args.host}:{args.port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
