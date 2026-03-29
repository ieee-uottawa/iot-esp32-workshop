#include <WiFi.h>
#include <PubSubClient.h>
#include <HCSR04.h>

// ----------- WiFi -----------
const char* ssid = "YOUR_WIFI";
const char* password = "YOUR_PASSWORD";

// ----------- MQTT -----------
const char* mqtt_server = "192.168.1.100"; // your broker IP

WiFiClient espClient;
PubSubClient client(espClient);

// ----------- Pins -----------
#define TRIG_PIN 5
#define ECHO_PIN 18
#define LED_PIN 2

// ----------- Device Config -----------
const char* device_id = "esp32_1";
float threshold = 20.0; // cm (default)
const char* distanceTopic = "sensors/esp32_1/distance";
const char* thresholdConfigTopic = "config/esp32_1/threshold";

// ----------- Sensor Setup -----------
UltraSonicDistanceSensor distanceSensor(TRIG_PIN, ECHO_PIN);

// ----------- MQTT Callback -----------
void callback(char* topic, byte* payload, unsigned int length) {
  String msg;

  for (int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }

  Serial.print("Message received: ");
  Serial.println(msg);

  if (String(topic) == thresholdConfigTopic) {
    threshold = msg.toFloat();
    Serial.print("New threshold: ");
    Serial.println(threshold);
  }
}

// ----------- Reconnect MQTT -----------
void reconnect() {
  while (!client.connected()) {
    Serial.print("Connecting to MQTT...");

    if (client.connect(device_id)) {
      Serial.println("connected");

      client.subscribe(thresholdConfigTopic);

    } else {
      Serial.println("failed, retrying...");
      delay(2000);
    }
  }
}

// ----------- Setup -----------
void setup() {
  Serial.begin(115200);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(LED_PIN, OUTPUT);

  // WiFi connect
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nConnected!");

  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}

// ----------- Loop -----------
void loop() {
  if (!client.connected()) {
    reconnect();
  }

  client.loop();

  float distance = distanceSensor.measureDistanceCm();

  // Convert to string
  String payload = String(distance);

  // Publish
  client.publish(distanceTopic, payload.c_str());

  Serial.print("Distance: ");
  Serial.println(distance);

  // LED logic
  if (distance < threshold) {
    digitalWrite(LED_PIN, HIGH);
  } else {
    digitalWrite(LED_PIN, LOW);
  }

  delay(1000);
}