"""
MQTT Subscriber Example

Usage:
    python subscribe.py

Description:
    Subscribes to the topic 'test/topic' on the MQTT broker (default: localhost:1883) and prints received messages.
    Edit BROKER, PORT, and TOPIC variables as needed.
    Requires paho-mqtt: pip install paho-mqtt
"""
import paho.mqtt.client as mqtt

BROKER = "localhost"   # or your broker IP
PORT = 1883
TOPIC = "test/topic"

# Callback when connected
def on_connect(client, userdata, flags, rc):
    print("Connected with result code", rc)
    client.subscribe(TOPIC)

# Callback when message received
def on_message(client, userdata, msg):
    print(f"Received: {msg.payload.decode()} on topic {msg.topic}")

client = mqtt.Client()

client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, 60)

print("Listening...")
client.loop_forever()