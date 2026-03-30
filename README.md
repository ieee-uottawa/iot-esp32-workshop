# IoT ESP32 Workshop

This project contains:

- ESP32 firmware (`src/main.cpp`) that publishes distance sensor readings to MQTT.
- A Python CLI backend (`backend.py`) to monitor all devices and set per-device thresholds.
- A Flask web dashboard (`dashboard.py`) for a live UI and threshold control.
- A simulator (`simulator.py`) to test everything without physical ESP32 hardware.

## What This System Does

The system uses MQTT topics to exchange data and configuration.

- Sensor data topic format:
  - `sensors/<device_id>/<sensor_name>`
  - Current firmware publishes distance to `sensors/esp32_1/distance`.
- Threshold configuration topic format:
  - `config/<device_id>/threshold`
  - Example: `config/esp32_1/threshold`

How data flows:

1. Device (real or simulated) publishes sensor readings to `sensors/...`.
2. Backend CLI and Dashboard subscribe to `sensors/+/+` to see all devices.
3. CLI/Dashboard publish threshold values to `config/<device_id>/threshold`.
4. Device (real or simulated) receives new threshold and updates its behavior.

## Project Structure

- `src/main.cpp`: ESP32 firmware (Wi-Fi + MQTT + HC-SR04 logic).
- `platformio.ini`: PlatformIO build config.
- `backend.py`: Terminal backend with commands and live table view.
- `dashboard.py`: Flask app with live web dashboard.
- `templates/dashboard.html`: Dashboard UI template.
- `publish.py`: Simple MQTT publisher example (sends test messages).
- `subscribe.py`: Simple MQTT subscriber example (prints received messages).
- `simulator.py`: Fake ESP32 devices for local testing.
- `run_demo.sh`: One-command launcher for simulator + backend + dashboard.
- `stop_demo.sh`: Stops all services started by `run_demo.sh`.
- `workshop.conf`: Example Mosquitto config.
- `requirements.txt`: Python dependencies for backend/dashboard/simulator.

## Prerequisites

- Python 3.10+ (tested with Python 3.12).
- An MQTT broker (Mosquitto recommended).
- For firmware deployment only: PlatformIO + ESP32 board.

## Python Setup (venv + packages)

From the project root:

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

To leave the environment:

```bash
deactivate
```

## MQTT Broker Setup

If you already have a broker, skip this section.

### Option A: Use your existing broker

Use the broker IP/host with all scripts via `--broker`.

### Option B: Run local Mosquitto (Linux)

Install and start Mosquitto (example):

```bash
sudo apt update
sudo apt install -y mosquitto mosquitto-clients
```

#### Use the provided workshop.conf

This repo includes a ready-to-use Mosquitto config for workshops:

- `workshop.conf` (in the project root)
  - Listens on port 1883
  - Allows anonymous connections (no password needed)

To enable it:

```bash
sudo cp workshop.conf /etc/mosquitto/conf.d/workshop.conf
sudo systemctl restart mosquitto
sudo systemctl status mosquitto
```

You can now use `localhost:1883` as your broker for all scripts and ESP32 devices.

## `publish.py` (MQTT Publisher Example)

Publishes 5 test messages to a topic on the MQTT broker (default: localhost:1883).

Usage:

```bash
python publish.py
```

Edit the BROKER, PORT, and TOPIC variables in the script as needed.

## `subscribe.py` (MQTT Subscriber Example)

Subscribes to a topic on the MQTT broker (default: localhost:1883) and prints received messages.

Usage:

```bash
python subscribe.py
```

Edit the BROKER, PORT, and TOPIC variables in the script as needed.

---

## `simulator.py` (No Hardware Testing)

Simulates one or more ESP32-style devices.

What it does:

- Publishes distance to `sensors/<device_id>/distance`.
- Subscribes to `config/+/threshold`.
- Updates each device threshold when config messages arrive.

Common commands:

```bash
python simulator.py --broker 192.168.1.100
python simulator.py --broker 192.168.1.100 --devices esp32_1,esp32_2,esp32_3
python simulator.py --broker 192.168.1.100 --count 5 --interval 0.5
```

Useful options:

- `--devices`: comma-separated IDs.
- `--count`: auto-create `esp32_1..esp32_N` when `--devices` is not set.
- `--interval`: publish period in seconds.
- `--min-distance`, `--max-distance`, `--jitter`: control value range and movement.
- `--default-threshold`: starting threshold for all simulated devices (default `20.0`).

## `backend.py` (CLI Backend)

Subscribes to all sensor data and lets you set thresholds from terminal.

Run:

```bash
python backend.py --broker 192.168.1.100
```

Optional auth:

```bash
python backend.py --broker 192.168.1.100 --username myuser --password mypass
```

Default threshold behavior:

- Backend assumes `20.0` for a device until you explicitly set one.
- Override with `--default-threshold` if needed.

CLI commands:

- `help`: show command list.
- `list`: print latest readings JSON.
- `live [seconds]`: live table view in terminal (default refresh `1.0s`).
- `set <device_id> <threshold>`: publish threshold to `config/<device_id>/threshold`.
- `quit` or `exit`: close backend.

Background mode:

- `--no-cli`: run backend without interactive prompt (used by demo launcher).

Example:

```text
set esp32_2 35
```

## `dashboard.py` (Web UI)

Flask dashboard with live updates and threshold form.

Run:

```bash
python dashboard.py --broker 192.168.1.100
```

Open in browser:

- `http://127.0.0.1:5000`

Features:

- Live stream of readings from all devices.
- Table view: device, sensor, value, threshold, time, topic.
- Form to set threshold for a selected device.

Useful options:

- `--host 0.0.0.0` to access from other machines on LAN.
- `--web-port 5001` to change web port.
- `--sensor-topic` to customize topic filter.
- `--default-threshold` sets fallback threshold shown for devices (default `20.0`).

Example:

```bash
python dashboard.py --broker 192.168.1.100 --host 0.0.0.0 --web-port 5001
```

## End-to-End Test Without Hardware

Open 2-3 terminals in project root and activate the same venv in each.

Terminal 1: start simulator

```bash
source venv/bin/activate
python simulator.py --broker 127.0.0.1 --count 3
```

Terminal 2: start backend CLI

```bash
source venv/bin/activate
python backend.py --broker 127.0.0.1
```

Then in backend CLI:

```text
live
set esp32_1 30
```

Terminal 3 (optional): start dashboard

```bash
source venv/bin/activate
python dashboard.py --broker 127.0.0.1
```

Open `http://127.0.0.1:5000` and use the form to set thresholds.

## One-Command Demo Runner

If you want to launch everything at once, use:

```bash
./run_demo.sh
```

By default, this starts:

- `simulator.py` (unless `--count 0`)
- `dashboard.py` (web UI)

**The backend CLI (`backend.py`) is NOT started by default.**
If you want to run it in the background for extra logging or CLI testing, add `--with-backend`:

```bash
./run_demo.sh --with-backend
```

Default values used by the launcher:

- broker: `127.0.0.1`
- port: `1883`
- simulated devices: `3`
- dashboard: `http://127.0.0.1:5000`

Notes:

- `--count 0` disables `simulator.py` in `run_demo.sh` so only real ESP32 publishers are used.
- `simulator.py` by itself still expects `--count >= 1` unless `--devices` is provided.
- `--with-backend` starts `backend.py` in background (optional, default: off).

Common options:

```bash
# Simulate 5 devices, dashboard on all interfaces
./run_demo.sh --broker 192.168.1.100 --port 1883 --count 5 --web-host 0.0.0.0 --web-port 5001

# Real ESP32 only (no simulator)
./run_demo.sh --broker 192.168.1.100 --port 1883 --count 0 --web-host 0.0.0.0 --web-port 5001

# With backend CLI in background
./run_demo.sh --with-backend
```

Stop everything:

```bash
./stop_demo.sh
```

Logs are written to:

- `.demo/logs/simulator.log` (if simulator enabled)
- `.demo/logs/backend.log` (if --with-backend)
- `.demo/logs/dashboard.log`

## Using Real ESP32 Firmware

Firmware file: `src/main.cpp`

Current firmware behavior:

- Connects to Wi-Fi using values in code (`ssid`, `password`).
- Publishes distance every second to `sensors/esp32_1/distance`.
- Subscribes to `config/esp32_1/threshold`.
- Turns LED on when `distance < threshold`.

Before flashing:

1. Set Wi-Fi credentials in `src/main.cpp`.
2. Set broker IP in `src/main.cpp` (`mqtt_server`).
3. Optionally change `device_id` and matching topics.

Build/upload with PlatformIO (example):

```bash
pio run
pio run --target upload
pio device monitor -b 115200
```

## MQTT Topic Reference

- Device publishes:
  - `sensors/<device_id>/distance` -> numeric payload (cm)
- Backend/dashboard subscribe:
  - `sensors/+/+`
- Backend/dashboard publish config:
  - `config/<device_id>/threshold` -> numeric payload
- Device/simulator subscribe config:
  - real firmware: `config/<device_id>/threshold`
  - simulator: `config/+/threshold`

## Troubleshooting

- `Import "paho.mqtt.client" could not be resolved`:
  - Activate venv and run `pip install -r requirements.txt`.
- No data appears in backend/dashboard:
  - Verify broker is running and reachable.
  - Ensure all scripts use the same `--broker` and `--port`.
  - Confirm simulator/ESP32 is publishing to `sensors/...` topics.
- Threshold updates do not apply:
  - Confirm exact `device_id` (for example `esp32_1`).
  - Check that config topic matches `config/<device_id>/threshold`.
- Dashboard not reachable from another device:
  - Run with `--host 0.0.0.0` and allow firewall access to chosen port.

## Quick Command Summary

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Simulate devices
python simulator.py --broker 127.0.0.1 --count 3

# CLI backend
python backend.py --broker 127.0.0.1

# Web dashboard
python dashboard.py --broker 127.0.0.1

# One-command demo
./run_demo.sh
./stop_demo.sh
```
