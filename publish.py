"""
MQTT Publisher Example

Usage:
    python publish.py

Description:
    Publishes 5 test messages to the topic 'test/topic' on the MQTT broker (default: localhost:1883).
    Edit BROKER, PORT, and TOPIC variables as needed.
    Requires paho-mqtt: pip install paho-mqtt
"""
import paho.mqtt.client as mqtt
import time

BROKER = "localhost"
PORT = 1883
TOPIC = "test/topic"

client = mqtt.Client()
client.connect(BROKER, PORT, 60)

for i in range(5):
    message = f"Hello MQTT {i}"
    client.publish(TOPIC, message)
    print("Sent:", message)
    time.sleep(1)

client.disconnect()