# PlasticLoop ESP32 node

Weighing scale (HX711 + load cell) and fill-level sensor (HC-SR04) for a collection point, reporting over MQTT or HTTPS.

```bash
arduino-cli lib install PubSubClient HX711 ArduinoJson
arduino-cli compile --fqbn esp32:esp32:esp32 plasticloop_node
arduino-cli upload  --fqbn esp32:esp32:esp32 -p <PORT> plasticloop_node
```

No credentials are compiled in: provision Wi-Fi, device ID/key and broker over USB serial (`help`).
Wiring, provisioning, calibration and the data contract: [docs/ESP32_INTEGRATION.md](../../docs/ESP32_INTEGRATION.md).
Compiled with esp32 core 3.0.0; not yet tested on physical hardware.
