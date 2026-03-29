#!/usr/bin/env python3
"""
Flask + MQTT live dashboard for the IoT workshop.

Features:
- Live sensor view for all devices (subscribes to sensors/+/+)
- Device threshold control from web UI (publishes config/<device_id>/threshold)
- Server-Sent Events stream for near real-time updates

Run:
  pip install flask paho-mqtt
  python dashboard.py --broker 192.168.1.100

Open:
  http://127.0.0.1:5000
"""

from __future__ import annotations

import argparse
import json
import queue
import threading
import time
from datetime import datetime
from typing import Any

from flask import Flask, Response, jsonify, render_template, request
import paho.mqtt.client as mqtt


app = Flask(__name__)


class DashboardState:
    def __init__(self, default_threshold: float) -> None:
        self.lock = threading.Lock()
        self.default_threshold = default_threshold
        self.latest_readings: dict[str, dict[str, dict[str, Any]]] = {}
        self.thresholds: dict[str, float] = {}
        self.subscribers: list[queue.Queue[str]] = []

    def _snapshot_json(self) -> str:
        payload = {
            "readings": self.latest_readings,
            "thresholds": self.thresholds,
            "default_threshold": self.default_threshold,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }
        return json.dumps(payload)

    def add_or_update_reading(self, device_id: str, sensor_name: str, raw_value: str, topic: str) -> None:
        try:
            value: Any = float(raw_value)
        except ValueError:
            value = raw_value

        record = {
            "value": value,
            "raw": raw_value,
            "topic": topic,
            "received_at": datetime.now().isoformat(timespec="seconds"),
        }

        with self.lock:
            if device_id not in self.latest_readings:
                self.latest_readings[device_id] = {}
            self.latest_readings[device_id][sensor_name] = record
            self._broadcast_locked(self._snapshot_json())

    def set_threshold(self, device_id: str, threshold: float) -> None:
        with self.lock:
            self.thresholds[device_id] = threshold
            self._broadcast_locked(self._snapshot_json())

    def get_snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "readings": self.latest_readings,
                "thresholds": self.thresholds,
                "default_threshold": self.default_threshold,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            }

    def subscribe(self) -> queue.Queue[str]:
        q: queue.Queue[str] = queue.Queue(maxsize=10)
        with self.lock:
            self.subscribers.append(q)
            # Send initial state immediately.
            q.put(self._snapshot_json())
        return q

    def unsubscribe(self, q: queue.Queue[str]) -> None:
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def _broadcast_locked(self, payload: str) -> None:
        stale: list[queue.Queue[str]] = []
        for q in self.subscribers:
            try:
                q.put_nowait(payload)
            except queue.Full:
                stale.append(q)

        for q in stale:
            self.subscribers.remove(q)


class MqttBridge:
    def __init__(self, state: DashboardState, broker: str, port: int, username: str | None, password: str | None, sensor_topic: str) -> None:
        self.state = state
        self.broker = broker
        self.port = port
        self.sensor_topic = sensor_topic
        self.connected = False

        client_id = f"iot-dashboard-{int(time.time())}"
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
            self.connected = False
            return

        self.connected = True
        print(f"[MQTT] Connected to {self.broker}:{self.port}")
        result, _ = client.subscribe(self.sensor_topic)
        if result == mqtt.MQTT_ERR_SUCCESS:
            print(f"[MQTT] Subscribed to '{self.sensor_topic}'")
        else:
            print(f"[MQTT] Subscribe failed for '{self.sensor_topic}'")

    def on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        self.connected = False
        print(f"[MQTT] Disconnected: reason_code={reason_code}")

    def on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace").strip()

        parts = topic.split("/")
        if len(parts) < 3 or parts[0] != "sensors":
            return

        device_id = parts[1]
        sensor_name = "/".join(parts[2:])
        self.state.add_or_update_reading(device_id, sensor_name, payload, topic)

    def start(self) -> None:
        print(f"[MQTT] Connecting to {self.broker}:{self.port}...")
        self.client.connect(self.broker, self.port, keepalive=60)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def publish_threshold(self, device_id: str, threshold: float) -> tuple[bool, str]:
        topic = f"config/{device_id}/threshold"
        result = self.client.publish(topic, payload=f"{threshold}", qos=1, retain=False)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            self.state.set_threshold(device_id, threshold)
            return True, topic
        return False, topic


STATE: DashboardState | None = None
MQTT_BRIDGE: MqttBridge | None = None


@app.route("/")
def index() -> str:
    return render_template("dashboard.html")


@app.route("/api/state", methods=["GET"])
def api_state() -> Response:
    if STATE is None:
        return jsonify({"error": "state is not initialized"}), 500
    return jsonify(STATE.get_snapshot())


@app.route("/api/threshold", methods=["POST"])
def api_threshold() -> Response:
    global MQTT_BRIDGE
    if MQTT_BRIDGE is None:
        return jsonify({"ok": False, "error": "MQTT bridge is not initialized"}), 500

    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "")).strip()
    threshold_raw = data.get("threshold")

    if not device_id:
        return jsonify({"ok": False, "error": "device_id is required"}), 400

    try:
        threshold = float(threshold_raw)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "threshold must be a number"}), 400

    ok, topic = MQTT_BRIDGE.publish_threshold(device_id, threshold)
    if not ok:
        return jsonify({"ok": False, "error": f"publish failed for topic '{topic}'"}), 500

    return jsonify({"ok": True, "device_id": device_id, "threshold": threshold, "topic": topic})


@app.route("/events")
def sse_events() -> Response:
    if STATE is None:
        return Response("event: error\ndata: {\"error\": \"state is not initialized\"}\n\n", mimetype="text/event-stream")

    q = STATE.subscribe()

    def event_stream() -> Any:
        try:
            while True:
                payload = q.get(timeout=30)
                yield f"data: {payload}\n\n"
        except queue.Empty:
            # Keep the connection alive.
            yield "event: ping\ndata: {}\n\n"
            yield from event_stream()
        finally:
            STATE.unsubscribe(q)

    return Response(event_stream(), mimetype="text/event-stream")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flask MQTT live dashboard")
    parser.add_argument("--broker", default="localhost", help="MQTT broker host/IP")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--username", default=None, help="MQTT username")
    parser.add_argument("--password", default=None, help="MQTT password")
    parser.add_argument("--sensor-topic", default="sensors/+/+", help="Sensor topic filter")
    parser.add_argument(
        "--default-threshold",
        type=float,
        default=20.0,
        help="Default threshold shown for devices before explicit config (default: 20.0)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Flask host")
    parser.add_argument("--web-port", type=int, default=5000, help="Flask port")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    return parser.parse_args()


def main() -> int:
    global STATE, MQTT_BRIDGE
    args = parse_args()

    STATE = DashboardState(default_threshold=args.default_threshold)

    MQTT_BRIDGE = MqttBridge(
        state=STATE,
        broker=args.broker,
        port=args.port,
        username=args.username,
        password=args.password,
        sensor_topic=args.sensor_topic,
    )

    try:
        MQTT_BRIDGE.start()
    except Exception as exc:
        print(f"[ERROR] Could not start MQTT bridge: {exc}")
        return 1

    try:
        app.run(host=args.host, port=args.web_port, debug=args.debug)
    finally:
        MQTT_BRIDGE.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
