#!/usr/bin/env python3
"""
ESP32 device simulator for MQTT testing.

This script simulates one or more ESP32-like devices that publish sensor data to:
  sensors/<device_id>/distance

It also listens for threshold updates on:
  config/<device_id>/threshold

Usage examples:
  python simulator.py --broker 192.168.1.100
  python simulator.py --broker 192.168.1.100 --devices esp32_1,esp32_2,esp32_3
  python simulator.py --broker 192.168.1.100 --count 5 --interval 0.5
"""

from __future__ import annotations

import argparse
import random
import signal
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import paho.mqtt.client as mqtt


@dataclass
class SimDevice:
    device_id: str
    threshold: float
    value: float


class Esp32Simulator:
    def __init__(
        self,
        broker: str,
        port: int,
        username: str | None,
        password: str | None,
        devices: list[str],
        interval: float,
        min_distance: float,
        max_distance: float,
        jitter: float,
        default_threshold: float,
    ) -> None:
        self.broker = broker
        self.port = port
        self.interval = interval
        self.min_distance = min_distance
        self.max_distance = max_distance
        self.jitter = jitter
        self.stop_event = threading.Event()

        self.devices: dict[str, SimDevice] = {}
        for device_id in devices:
            start_value = random.uniform(min_distance, max_distance)
            self.devices[device_id] = SimDevice(
                device_id=device_id,
                threshold=default_threshold,
                value=start_value,
            )

        client_id = f"esp32-simulator-{int(time.time())}"
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
        result, _ = client.subscribe("config/+/threshold", qos=1)
        if result == mqtt.MQTT_ERR_SUCCESS:
            print("[MQTT] Subscribed to 'config/+/threshold'")
        else:
            print("[MQTT] Failed to subscribe to 'config/+/threshold'")

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
        else:
            print(f"[MQTT] Disconnected unexpectedly: reason_code={reason_code}")

    def on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace").strip()

        parts = topic.split("/")
        if len(parts) != 3 or parts[0] != "config" or parts[2] != "threshold":
            return

        device_id = parts[1]
        if device_id not in self.devices:
            print(f"[CONFIG] Ignored threshold for unknown device '{device_id}'")
            return

        try:
            threshold = float(payload)
        except ValueError:
            print(f"[CONFIG] Invalid threshold payload for {device_id}: '{payload}'")
            return

        self.devices[device_id].threshold = threshold
        print(f"[CONFIG] {device_id} threshold updated -> {threshold}")

    def start(self) -> None:
        print(f"[MQTT] Connecting to {self.broker}:{self.port} ...")
        self.client.connect(self.broker, self.port, keepalive=60)
        self.client.loop_start()

    def stop(self) -> None:
        self.stop_event.set()
        self.client.loop_stop()
        self.client.disconnect()

    def _next_value(self, current: float) -> float:
        # Random walk for smoother simulated measurements.
        delta = random.uniform(-self.jitter, self.jitter)
        next_value = current + delta
        return max(self.min_distance, min(self.max_distance, next_value))

    def publish_loop(self) -> None:
        print(f"[SIM] Publishing for devices: {', '.join(self.devices.keys())}")
        print("[SIM] Press Ctrl+C to stop.")

        while not self.stop_event.is_set():
            now = datetime.now().isoformat(timespec="seconds")
            for device in self.devices.values():
                device.value = self._next_value(device.value)
                topic = f"sensors/{device.device_id}/distance"
                payload = f"{device.value:.2f}"
                self.client.publish(topic, payload=payload, qos=0, retain=False)

                state = "ALERT" if device.value < device.threshold else "OK"
                print(
                    f"[{now}] {device.device_id} distance={payload}cm "
                    f"threshold={device.threshold:.2f} state={state}"
                )

            time.sleep(self.interval)


def parse_devices(raw_devices: str | None, count: int) -> list[str]:
    if raw_devices:
        items = [item.strip() for item in raw_devices.split(",") if item.strip()]
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        if not deduped:
            raise ValueError("--devices was provided but no valid device IDs were found")
        return deduped

    if count < 1:
        raise ValueError("--count must be >= 1")

    return [f"esp32_{i}" for i in range(1, count + 1)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ESP32 MQTT simulator")
    parser.add_argument("--broker", default="localhost", help="MQTT broker host/IP")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--username", default=None, help="MQTT username (optional)")
    parser.add_argument("--password", default=None, help="MQTT password (optional)")

    parser.add_argument(
        "--devices",
        default=None,
        help="Comma-separated device IDs (example: esp32_1,esp32_2)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Number of auto-generated devices if --devices is not set (default: 3)",
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds between publish cycles (default: 1.0)",
    )
    parser.add_argument(
        "--min-distance",
        type=float,
        default=5.0,
        help="Minimum simulated distance in cm (default: 5.0)",
    )
    parser.add_argument(
        "--max-distance",
        type=float,
        default=200.0,
        help="Maximum simulated distance in cm (default: 200.0)",
    )
    parser.add_argument(
        "--jitter",
        type=float,
        default=8.0,
        help="Max random +/- change per cycle in cm (default: 8.0)",
    )
    parser.add_argument(
        "--default-threshold",
        type=float,
        default=20.0,
        help="Initial threshold for all simulated devices (default: 20.0)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.interval <= 0:
        print("[ERROR] --interval must be > 0")
        return 1
    if args.min_distance >= args.max_distance:
        print("[ERROR] --min-distance must be < --max-distance")
        return 1
    if args.jitter < 0:
        print("[ERROR] --jitter must be >= 0")
        return 1

    try:
        devices = parse_devices(args.devices, args.count)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    sim = Esp32Simulator(
        broker=args.broker,
        port=args.port,
        username=args.username,
        password=args.password,
        devices=devices,
        interval=args.interval,
        min_distance=args.min_distance,
        max_distance=args.max_distance,
        jitter=args.jitter,
        default_threshold=args.default_threshold,
    )

    def handle_signal(signum: int, frame: Any) -> None:
        print(f"\n[SYSTEM] Received signal {signum}, shutting down...")
        sim.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        sim.start()
        sim.publish_loop()
    except Exception as exc:
        print(f"[ERROR] Simulator failed: {exc}")
        sim.stop()
        return 1

    sim.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
