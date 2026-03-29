#!/usr/bin/env python3
"""
Simple MQTT backend for the IoT workshop.

Features:
- Subscribes to sensor data from all devices (topic: sensors/<device_id>/<sensor_name>)
- Tracks and prints latest readings
- Publishes threshold updates for a specific device
  (topic: config/<device_id>/threshold)

Usage example:
  python backend.py --broker 192.168.1.100

Interactive commands:
  help
  list
  set <device_id> <threshold>
  quit
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
from datetime import datetime
from typing import Any

import paho.mqtt.client as mqtt


class MqttBackend:
    def __init__(
        self,
        broker: str,
        port: int,
        username: str | None,
        password: str | None,
        sensor_topic: str,
        default_threshold: float,
    ) -> None:
        self.broker = broker
        self.port = port
        self.sensor_topic = sensor_topic
        self.default_threshold = default_threshold
        self.latest_readings: dict[str, dict[str, dict[str, Any]]] = {}
        self.thresholds: dict[str, float] = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.live_mode = threading.Event()

        client_id = f"iot-workshop-backend-{threading.get_ident()}"
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)

        if username:
            self.client.username_pw_set(username=username, password=password)

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

    def on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        if reason_code != 0:
            print(f"[MQTT] Connection failed: reason_code={reason_code}")
            return

        print(f"[MQTT] Connected to {self.broker}:{self.port}")
        result, _ = client.subscribe(self.sensor_topic, qos=0)
        if result == mqtt.MQTT_ERR_SUCCESS:
            print(f"[MQTT] Subscribed to '{self.sensor_topic}'")
        else:
            print(f"[MQTT] Failed to subscribe to '{self.sensor_topic}'")

    def on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        if self.stop_event.is_set():
            print("[MQTT] Disconnected cleanly")
            return
        print(f"[MQTT] Disconnected unexpectedly: reason_code={reason_code}")

    def on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        msg: mqtt.MQTTMessage,
    ) -> None:
        topic = msg.topic
        payload_raw = msg.payload.decode("utf-8", errors="replace").strip()

        parts = topic.split("/")
        if len(parts) < 3 or parts[0] != "sensors":
            print(f"[DATA] Ignored topic '{topic}' payload='{payload_raw}'")
            return

        device_id = parts[1]
        sensor_name = "/".join(parts[2:])

        value: Any = payload_raw
        try:
            value = float(payload_raw)
        except ValueError:
            # Keep original string if not numeric.
            pass

        record = {
            "value": value,
            "raw": payload_raw,
            "topic": topic,
            "received_at": datetime.now().isoformat(timespec="seconds"),
        }

        with self.lock:
            if device_id not in self.latest_readings:
                self.latest_readings[device_id] = {}
            self.latest_readings[device_id][sensor_name] = record

        if not self.live_mode.is_set():
            print(
                f"[DATA] device={device_id} sensor={sensor_name} value={record['raw']} "
                f"time={record['received_at']}"
            )

    def start(self) -> None:
        print(f"[MQTT] Connecting to {self.broker}:{self.port} ...")
        self.client.connect(self.broker, self.port, keepalive=60)
        self.client.loop_start()

    def stop(self) -> None:
        self.stop_event.set()
        self.client.loop_stop()
        self.client.disconnect()

    def set_threshold(self, device_id: str, threshold: float) -> None:
        topic = f"config/{device_id}/threshold"
        payload = f"{threshold}"
        result = self.client.publish(topic, payload=payload, qos=1, retain=False)

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            with self.lock:
                self.thresholds[device_id] = threshold
            print(f"[CONFIG] Published threshold={threshold} to topic '{topic}'")
        else:
            print(f"[CONFIG] Failed to publish threshold to topic '{topic}'")

    def print_latest(self) -> None:
        with self.lock:
            if not self.latest_readings:
                print("[DATA] No sensor data received yet.")
                return

            print("[DATA] Latest sensor readings:")
            print(json.dumps(self.latest_readings, indent=2))

    def build_rows(self) -> list[dict[str, str]]:
        with self.lock:
            rows: list[dict[str, str]] = []
            for device_id, sensors in self.latest_readings.items():
                threshold = self.thresholds.get(device_id, self.default_threshold)
                threshold_str = str(threshold)
                for sensor_name, record in sensors.items():
                    rows.append(
                        {
                            "device": device_id,
                            "sensor": sensor_name,
                            "value": str(record.get("raw", "-")),
                            "threshold": threshold_str,
                            "time": str(record.get("received_at", "-")),
                        }
                    )

            rows.sort(key=lambda row: (row["device"], row["sensor"]))
            return rows


def render_live_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "No sensor data received yet."

    headers = ["Device", "Sensor", "Value", "Threshold", "Time"]
    keys = ["device", "sensor", "value", "threshold", "time"]
    widths = [len(header) for header in headers]

    for row in rows:
        for idx, key in enumerate(keys):
            widths[idx] = max(widths[idx], len(row[key]))

    sep = "-+-".join("-" * width for width in widths)
    header_line = " | ".join(headers[idx].ljust(widths[idx]) for idx in range(len(headers)))
    body = [
        " | ".join(row[keys[idx]].ljust(widths[idx]) for idx in range(len(keys)))
        for row in rows
    ]
    return "\n".join([header_line, sep, *body])


def clear_terminal() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def run_live_view(backend: MqttBackend, refresh_seconds: float) -> None:
    backend.live_mode.set()
    try:
        while True:
            clear_terminal()
            now = datetime.now().isoformat(timespec="seconds")
            print("IoT Backend Live View")
            print(f"Updated: {now}")
            print(f"Refresh: {refresh_seconds:.1f}s")
            print("Press Ctrl+C to return to command prompt.")
            print()
            print(render_live_table(backend.build_rows()))
            time.sleep(refresh_seconds)
    except KeyboardInterrupt:
        print("\n[SYSTEM] Leaving live view...")
    finally:
        backend.live_mode.clear()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MQTT backend for IoT workshop")
    parser.add_argument(
        "--broker",
        default="localhost",
        help="MQTT broker hostname or IP (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=1883,
        help="MQTT broker port (default: 1883)",
    )
    parser.add_argument(
        "--username",
        default=None,
        help="MQTT username (optional)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="MQTT password (optional)",
    )
    parser.add_argument(
        "--sensor-topic",
        default="sensors/+/+",
        help="MQTT topic filter for sensor data (default: sensors/+/+)",
    )
    parser.add_argument(
        "--default-threshold",
        type=float,
        default=20.0,
        help="Default threshold to assume for devices before explicit config (default: 20.0)",
    )
    parser.add_argument(
        "--no-cli",
        action="store_true",
        help="Run backend without interactive prompt (useful for background demos)",
    )
    return parser.parse_args()


def print_help() -> None:
    print("Commands:")
    print("  help                         Show commands")
    print("  list                         Show latest sensor readings")
    print("  live [seconds]               Live table view (default refresh: 1s)")
    print("  set <device_id> <threshold>  Configure threshold for one device")
    print("  quit                         Exit backend")


def main() -> int:
    args = parse_args()
    backend = MqttBackend(
        broker=args.broker,
        port=args.port,
        username=args.username,
        password=args.password,
        sensor_topic=args.sensor_topic,
        default_threshold=args.default_threshold,
    )

    def handle_signal(signum: int, frame: Any) -> None:
        print(f"\n[SYSTEM] Received signal {signum}, shutting down...")
        backend.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        backend.start()
    except Exception as exc:
        print(f"[ERROR] Could not start backend: {exc}")
        return 1

    if args.no_cli:
        print("[SYSTEM] Backend running in no-cli mode. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[SYSTEM] Exiting...")
            backend.stop()
            return 0

    print_help()

    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[SYSTEM] Exiting...")
            break

        if not raw:
            continue

        if raw in {"quit", "exit"}:
            break

        if raw == "help":
            print_help()
            continue

        if raw == "list":
            backend.print_latest()
            continue

        if raw.startswith("live"):
            parts = raw.split()
            refresh_seconds = 1.0

            if len(parts) > 2:
                print("[ERROR] Usage: live [seconds]")
                continue

            if len(parts) == 2:
                try:
                    refresh_seconds = float(parts[1])
                    if refresh_seconds <= 0:
                        raise ValueError
                except ValueError:
                    print("[ERROR] seconds must be a positive number")
                    continue

            run_live_view(backend, refresh_seconds)
            continue

        if raw.startswith("set "):
            parts = raw.split()
            if len(parts) != 3:
                print("[ERROR] Usage: set <device_id> <threshold>")
                continue

            device_id = parts[1]
            try:
                threshold = float(parts[2])
            except ValueError:
                print("[ERROR] threshold must be a number")
                continue

            backend.set_threshold(device_id, threshold)
            continue

        print("[ERROR] Unknown command. Type 'help' for options.")

    backend.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
