#!/usr/bin/env python3
"""PlasticLoop SIMULATED IoT node (stands in for the ESP32 firmware; every payload carries "synthetic": true).

Speaks the same contract as firmware/esp32/plasticloop_node: MQTT topics
plasticloop/devices/<id>/{telemetry,status,commands} or HTTPS POST /api/v1/devices/telemetry.

    # inside the stack (demo keys derive from DEMO_DEVICE_SECRET):
    docker compose exec api python /simulators/iot-device/simulator.py --device-id DEV-ESP32-001 --demo-key
    # from a laptop against a remote broker:
    python simulator.py --device-id DEV-ESP32-010 --key <key> --mqtt-host 192.168.1.20 --mqtt-port 1883
    python simulator.py --device-id DEV-ESP32-010 --key <key> --transport https --api-url http://localhost:8000

Interactive keys (type + Enter while running):
    w <kg>   set weight        f <pct>  set fill         b <pct>  set battery
    e        toggle sensor error          n        toggle network drop (readings buffered, sent on reconnect)
    o        go offline (stop; broker publishes last will)              s        send one reading now
    q        quit
"""

import argparse
import hashlib
import hmac
import json
import os
import queue
import random
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime

try:
    import paho.mqtt.client as mqtt
except ImportError:  # HTTPS mode works with the stdlib only
    mqtt = None


class Node:
    def __init__(self, args):
        self.args = args
        self.weight = args.weight
        self.fill = args.fill
        self.battery = args.battery
        self.sensor_error = False
        self.network_down = False
        self.interval = args.interval
        self.scale_offset = 0.0
        self.buffer: list[dict] = []  # ring buffer while the network is "down" (firmware keeps 50)
        self.inbox: queue.Queue = queue.Queue()
        self.client = None
        self.connected = threading.Event()
        self.refused = False
        self.base = f"plasticloop/devices/{args.device_id}"

    # ---------- payloads ----------
    def reading(self) -> dict:
        self.weight = max(0.0, self.weight + random.uniform(0.0, 0.6))
        self.fill = min(100.0, self.fill + random.uniform(0.2, 1.2))
        self.battery = max(0, self.battery - random.choice([0, 0, 1]))
        return {
            "device_id": self.args.device_id,
            "reading_id": f"{self.args.device_id}-{uuid.uuid4().hex[:12]}",
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "weight_kg": round(self.weight - self.scale_offset + random.gauss(0, 0.02), 3),
            "fill_percent": round(self.fill, 1),
            "battery_percent": self.battery,
            "sensor_status": "load_cell_error" if self.sensor_error else "ok",
            "firmware_version": "sim-1.0.0",
            "synthetic": True,
        }

    # ---------- transports ----------
    def connect(self):
        if self.args.transport != "mqtt":
            return
        if mqtt is None:
            sys.exit("paho-mqtt is not installed: pip install paho-mqtt (or use --transport https)")
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.args.device_id)
        c.username_pw_set(self.args.device_id, self.args.key)
        c.will_set(f"{self.base}/status", json.dumps({"status": "offline"}), qos=1, retain=True)
        c.on_connect = self.on_connect
        c.on_message = lambda _c, _u, msg: self.inbox.put(msg.payload)
        c.connect(self.args.mqtt_host, self.args.mqtt_port, keepalive=30)
        c.loop_start()
        self.client = c
        for _ in range(50):
            if self.connected.is_set() or self.refused:
                break
            time.sleep(0.1)
        if not self.connected.is_set():
            c.loop_stop()
            sys.exit("! could not connect to the broker; nothing was sent")

    def on_connect(self, client, _userdata, _flags, reason_code, _props):
        if reason_code.is_failure:
            print(f"! MQTT connect refused: {reason_code} (wrong key or device not provisioned?)")
            self.refused = True
            return
        self.connected.set()
        client.subscribe(f"{self.base}/commands", qos=1)
        client.publish(f"{self.base}/status", json.dumps({"status": "online", "firmware_version": "sim-1.0.0"}), qos=1, retain=True)
        print(f"✓ connected to {self.args.mqtt_host}:{self.args.mqtt_port} as {self.args.device_id}")

    def send(self, payload: dict) -> bool:
        if self.network_down:
            self.buffer = (self.buffer + [payload])[-50:]
            print(f"… network down, buffered {payload['reading_id']} ({len(self.buffer)} queued)")
            return False
        if self.args.transport == "mqtt":
            info = self.client.publish(f"{self.base}/telemetry", json.dumps(payload), qos=1)
            ok = info.rc == mqtt.MQTT_ERR_SUCCESS
        else:
            req = urllib.request.Request(
                f"{self.args.api_url.rstrip('/')}/api/v1/devices/telemetry", data=json.dumps(payload).encode(), method="POST",
                headers={"Content-Type": "application/json", "Authorization": f"Device {self.args.device_id}:{self.args.key}"})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    ack = json.loads(resp.read())
                    ok = True
                    print(f"  server: {ack['status']} quality={ack['quality']}")
            except urllib.error.HTTPError as exc:
                print(f"! HTTP {exc.code}: {exc.read().decode()[:200]}")
                return False
            except OSError as exc:
                print(f"! network error: {exc}")
                ok = False
        if ok:
            print(f"→ {payload['reading_id']} weight={payload['weight_kg']}kg fill={payload['fill_percent']}% "
                  f"battery={payload['battery_percent']}% sensor={payload['sensor_status']} [SIMULATED]")
        return ok

    def flush_buffer(self):
        while self.buffer and not self.network_down:
            if not self.send(self.buffer[0]):
                break
            self.buffer.pop(0)

    # ---------- commands (same semantics as the firmware) ----------
    def handle_commands(self):
        while not self.inbox.empty():
            try:
                cmd = json.loads(self.inbox.get_nowait())
            except ValueError:
                continue
            name = cmd.get("command")
            print(f"← command {name} {cmd}")
            if name == "tare":
                self.scale_offset = self.weight
                self.status({"type": "calibration_result", "command": "tare", "result": "pass", "offset": self.scale_offset})
            elif name == "calibrate":
                ok = not self.sensor_error and cmd.get("known_mass_kg", 0) > 0
                self.status({"type": "calibration_result", "command": "calibrate", "result": "pass" if ok else "fail",
                             "reference_mass_kg": cmd.get("known_mass_kg"), "scale_factor": round(random.uniform(20, 23), 3)})
            elif name == "set_interval":
                self.interval = max(10, int(cmd.get("interval_s", self.interval)))
                self.status({"type": "command_ack", "command": name, "result": "pass"})
            elif name in ("ping", "reboot"):
                self.status({"type": "command_ack", "command": name, "result": "pass", "status": "online"})

    def status(self, msg: dict):
        if self.client:
            self.client.publish(f"{self.base}/status", json.dumps(msg), qos=1)

    # ---------- main loop ----------
    def run(self):
        self.connect()
        stop = threading.Event()
        if sys.stdin.isatty() and not self.args.count:
            threading.Thread(target=self.keyboard, args=(stop,), daemon=True).start()
            print(__doc__.split("Interactive keys")[1])
        sent, next_at = 0, 0.0
        while not stop.is_set():
            self.handle_commands()
            if time.monotonic() >= next_at:
                self.send(self.reading())
                sent += 1
                next_at = time.monotonic() + self.interval
                if self.args.count and sent >= self.args.count:
                    break
            time.sleep(0.2)
        if self.client:
            time.sleep(0.5)
            self.client.loop_stop()
            if not self.args.drop:
                self.client.disconnect()

    def keyboard(self, stop: threading.Event):
        for line in sys.stdin:
            parts = line.strip().split()
            if not parts:
                continue
            key, val = parts[0], (float(parts[1]) if len(parts) > 1 else None)
            if key == "w" and val is not None:
                self.weight = val
            elif key == "f" and val is not None:
                self.fill = max(0.0, min(100.0, val))
            elif key == "b" and val is not None:
                self.battery = int(max(0, min(100, val)))
            elif key == "e":
                self.sensor_error = not self.sensor_error
                print(f"sensor error {'ON' if self.sensor_error else 'off'}")
            elif key == "n":
                self.network_down = not self.network_down
                print(f"network {'DOWN' if self.network_down else 'up'}")
                self.flush_buffer()
            elif key == "s":
                self.send(self.reading())
            elif key == "o":
                self.args.drop = True  # skip clean disconnect so the broker publishes the last will
                stop.set()
            elif key == "q":
                stop.set()


def main():
    p = argparse.ArgumentParser(description="PlasticLoop SIMULATED device (synthetic data only)")
    p.add_argument("--device-id", required=True)
    p.add_argument("--key", help="Device key shown once at registration")
    p.add_argument("--demo-key", action="store_true", help="Derive the seeded demo key from DEMO_DEVICE_SECRET")
    p.add_argument("--transport", choices=["mqtt", "https"], default="mqtt")
    p.add_argument("--mqtt-host", default=os.environ.get("MQTT_HOST", "localhost"))
    p.add_argument("--mqtt-port", type=int, default=int(os.environ.get("MQTT_PORT", "1883")))
    p.add_argument("--api-url", default=os.environ.get("API_URL", "http://localhost:8000"))
    p.add_argument("--interval", type=float, default=10.0, help="Seconds between readings")
    p.add_argument("--count", type=int, default=0, help="Send N readings then exit (0 = run until q)")
    p.add_argument("--weight", type=float, default=12.0)
    p.add_argument("--fill", type=float, default=35.0)
    p.add_argument("--battery", type=int, default=90)
    p.add_argument("--drop", action="store_true", help="Exit without a clean disconnect (triggers last will)")
    args = p.parse_args()
    if args.demo_key:
        secret = os.environ.get("DEMO_DEVICE_SECRET")
        if not secret:
            sys.exit("DEMO_DEVICE_SECRET is not set")
        args.key = hmac.new(secret.encode(), args.device_id.encode(), hashlib.sha256).hexdigest()[:32]
    if not args.key:
        sys.exit("Provide --key (or --demo-key for seeded demo devices)")
    Node(args).run()


if __name__ == "__main__":
    main()
