/*
 * PlasticLoop AI — ESP32 collection-point node (weighing scale + fill-level sensor).
 *
 * Contract (same as simulators/iot-device/simulator.py):
 *   MQTT  plasticloop/devices/<id>/telemetry   (device → server)
 *         plasticloop/devices/<id>/status      (device → server, incl. last-will {"status":"offline"})
 *         plasticloop/devices/<id>/commands    (server → device: tare, calibrate, set_interval, reboot, ping)
 *   HTTPS POST <api_url>/api/v1/devices/telemetry with "Authorization: Device <id>:<key>" (transport=https)
 *
 * No credential is compiled in. Provision over USB serial (115200 baud), e.g.
 *   set wifi_ssid MyNetwork | set wifi_pass ******** | set device_id DEV-ESP32-010 | set device_key <key from the web app>
 *   set mqtt_host 192.168.1.20 | set mqtt_port 1883 | save | reboot          ("help" lists everything)
 * Values live in NVS (Preferences). Readings that cannot be sent are kept in a RAM ring buffer and re-sent; the
 * server de-duplicates on reading_id, so a resend can never double-count.
 *
 * Wiring (see firmware/esp32/README.md): HX711 DOUT=16 SCK=17 · HC-SR04 TRIG=5 ECHO=18 (ECHO through a 5V→3.3V divider!)
 * · battery sense on GPIO34 via a 100k/100k divider.
 */
#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <HX711.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <time.h>

#define FIRMWARE_VERSION "1.0.0"
#define PIN_HX711_DOUT 16
#define PIN_HX711_SCK 17
#define PIN_US_TRIG 5
#define PIN_US_ECHO 18
#define PIN_BATTERY 34
#define BUFFER_SLOTS 50

struct Config {
  String wifiSsid, wifiPass, deviceId, deviceKey, mqttHost, apiUrl, transport, caPem;
  uint16_t mqttPort = 1883;
  uint32_t intervalS = 300;
  float binDepthCm = 90.0f;
  float scaleFactor = 0.0f;  // 0 = not calibrated: weight is reported as null
  long scaleOffset = 0;
} cfg;

Preferences prefs;
HX711 scale;
WiFiClient plainClient;
WiFiClientSecure tlsClient;
PubSubClient mqtt;
String topicBase;
String ring[BUFFER_SLOTS];
int ringHead = 0, ringCount = 0;
uint32_t lastSendMs = 0, readingCounter = 0, lastConnectTryMs = 0;
bool sensorFault = false;

// ---------- configuration ----------
void loadConfig() {
  prefs.begin("plasticloop", true);
  cfg.wifiSsid = prefs.getString("wifi_ssid", "");
  cfg.wifiPass = prefs.getString("wifi_pass", "");
  cfg.deviceId = prefs.getString("device_id", "");
  cfg.deviceKey = prefs.getString("device_key", "");
  cfg.mqttHost = prefs.getString("mqtt_host", "");
  cfg.mqttPort = prefs.getUShort("mqtt_port", 1883);
  cfg.apiUrl = prefs.getString("api_url", "");
  cfg.transport = prefs.getString("transport", "mqtt");
  cfg.caPem = prefs.getString("ca_pem", "");
  cfg.intervalS = prefs.getUInt("interval_s", 300);
  cfg.binDepthCm = prefs.getFloat("bin_depth_cm", 90.0f);
  cfg.scaleFactor = prefs.getFloat("scale_factor", 0.0f);
  cfg.scaleOffset = prefs.getLong("scale_offset", 0);
  readingCounter = prefs.getUInt("counter", 0);
  prefs.end();
}

void saveConfig() {
  prefs.begin("plasticloop", false);
  prefs.putString("wifi_ssid", cfg.wifiSsid);
  prefs.putString("wifi_pass", cfg.wifiPass);
  prefs.putString("device_id", cfg.deviceId);
  prefs.putString("device_key", cfg.deviceKey);
  prefs.putString("mqtt_host", cfg.mqttHost);
  prefs.putUShort("mqtt_port", cfg.mqttPort);
  prefs.putString("api_url", cfg.apiUrl);
  prefs.putString("transport", cfg.transport);
  prefs.putString("ca_pem", cfg.caPem);
  prefs.putUInt("interval_s", cfg.intervalS);
  prefs.putFloat("bin_depth_cm", cfg.binDepthCm);
  prefs.putFloat("scale_factor", cfg.scaleFactor);
  prefs.putLong("scale_offset", cfg.scaleOffset);
  prefs.end();
}

void persistCounter() {
  prefs.begin("plasticloop", false);
  prefs.putUInt("counter", readingCounter);
  prefs.end();
}

bool configured() { return cfg.wifiSsid.length() && cfg.deviceId.length() && cfg.deviceKey.length(); }

// ---------- serial provisioning ----------
void printConfig() {
  Serial.printf("device_id=%s transport=%s mqtt=%s:%u api_url=%s interval_s=%u bin_depth_cm=%.1f\n", cfg.deviceId.c_str(),
                cfg.transport.c_str(), cfg.mqttHost.c_str(), cfg.mqttPort, cfg.apiUrl.c_str(), cfg.intervalS, cfg.binDepthCm);
  Serial.printf("wifi_ssid=%s wifi_pass=%s device_key=%s ca_pem=%s\n", cfg.wifiSsid.c_str(), cfg.wifiPass.length() ? "(set)" : "(empty)",
                cfg.deviceKey.length() ? "(set)" : "(empty)", cfg.caPem.length() ? "(set)" : "(none)");
  Serial.printf("calibrated=%s factor=%.4f offset=%ld buffered=%d\n", cfg.scaleFactor != 0 ? "yes" : "no", cfg.scaleFactor, cfg.scaleOffset, ringCount);
}

void handleSerialLine(String line) {
  line.trim();
  if (!line.length()) return;
  int sp = line.indexOf(' ');
  String cmd = sp < 0 ? line : line.substring(0, sp);
  String rest = sp < 0 ? "" : line.substring(sp + 1);
  if (cmd == "help") {
    Serial.println("set <wifi_ssid|wifi_pass|device_id|device_key|mqtt_host|mqtt_port|api_url|transport|interval_s|bin_depth_cm|ca_pem> <value>");
    Serial.println("show | save | tare | calibrate <known_kg> | reboot | factory_reset");
  } else if (cmd == "set") {
    int sp2 = rest.indexOf(' ');
    String key = sp2 < 0 ? rest : rest.substring(0, sp2);
    String val = sp2 < 0 ? "" : rest.substring(sp2 + 1);
    if (key == "wifi_ssid") cfg.wifiSsid = val;
    else if (key == "wifi_pass") cfg.wifiPass = val;
    else if (key == "device_id") cfg.deviceId = val;
    else if (key == "device_key") cfg.deviceKey = val;
    else if (key == "mqtt_host") cfg.mqttHost = val;
    else if (key == "mqtt_port") cfg.mqttPort = val.toInt();
    else if (key == "api_url") cfg.apiUrl = val;
    else if (key == "transport") cfg.transport = (val == "https") ? "https" : "mqtt";
    else if (key == "interval_s") cfg.intervalS = max(10L, val.toInt());
    else if (key == "bin_depth_cm") cfg.binDepthCm = val.toFloat();
    else if (key == "ca_pem") { val.replace("\\n", "\n"); cfg.caPem = val; }  // paste PEM on one line with \n escapes
    else { Serial.println("unknown key"); return; }
    Serial.println("ok (run 'save' to keep it)");
  } else if (cmd == "show") printConfig();
  else if (cmd == "save") { saveConfig(); Serial.println("saved"); }
  else if (cmd == "tare") { scale.tare(10); cfg.scaleOffset = scale.get_offset(); saveConfig(); Serial.println("tared"); }
  else if (cmd == "calibrate") {
    float known = rest.toFloat();
    if (known <= 0) { Serial.println("usage: calibrate <known_kg> (after tare, with the weight on the scale)"); return; }
    cfg.scaleFactor = (scale.read_average(15) - scale.get_offset()) / known;
    scale.set_scale(cfg.scaleFactor);
    saveConfig();
    Serial.printf("factor=%.4f\n", cfg.scaleFactor);
  } else if (cmd == "reboot") ESP.restart();
  else if (cmd == "factory_reset") { prefs.begin("plasticloop", false); prefs.clear(); prefs.end(); ESP.restart(); }
  else Serial.println("unknown command (help)");
}

void pollSerial() {
  static String line;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') { handleSerialLine(line); line = ""; }
    else if (line.length() < 4096) line += c;
  }
}

// ---------- sensors ----------
float readWeightKg(bool &ok) {
  ok = false;
  if (cfg.scaleFactor == 0 || !scale.wait_ready_timeout(1000)) return NAN;
  ok = true;
  return scale.get_units(10);
}

float readFillPercent(bool &ok) {
  digitalWrite(PIN_US_TRIG, LOW);
  delayMicroseconds(4);
  digitalWrite(PIN_US_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_US_TRIG, LOW);
  unsigned long us = pulseIn(PIN_US_ECHO, HIGH, 30000);
  ok = us > 0;
  if (!ok) return NAN;
  float distanceCm = us * 0.0343f / 2.0f;
  return constrain((cfg.binDepthCm - distanceCm) / cfg.binDepthCm * 100.0f, 0.0f, 100.0f);
}

int readBatteryPercent() {
  uint32_t mv = analogReadMilliVolts(PIN_BATTERY) * 2;  // 1:1 divider
  return constrain(map((long)mv, 3300, 4200, 0, 100), 0, 100);
}

bool clockValid() { return time(nullptr) > 1700000000; }

String isoNow() {
  time_t now = time(nullptr);
  struct tm t;
  gmtime_r(&now, &t);
  char buf[24];
  strftime(buf, sizeof buf, "%Y-%m-%dT%H:%M:%SZ", &t);
  return String(buf);
}

String buildReading() {
  bool wOk, fOk;
  float kg = readWeightKg(wOk);
  float fill = readFillPercent(fOk);
  JsonDocument doc;
  doc["device_id"] = cfg.deviceId;
  doc["reading_id"] = cfg.deviceId + "-" + String((uint32_t)time(nullptr)) + "-" + String(++readingCounter);
  doc["timestamp"] = isoNow();
  if (wOk) doc["weight_kg"] = roundf(kg * 1000) / 1000; else doc["weight_kg"] = nullptr;
  if (fOk) doc["fill_percent"] = roundf(fill * 10) / 10; else doc["fill_percent"] = nullptr;
  doc["battery_percent"] = readBatteryPercent();
  sensorFault = (cfg.scaleFactor != 0 && !wOk) || !fOk;
  doc["sensor_status"] = sensorFault ? (!fOk ? "ultrasonic_timeout" : "load_cell_error") : "ok";
  doc["firmware_version"] = FIRMWARE_VERSION;
  String out;
  serializeJson(doc, out);
  if (readingCounter % 20 == 0) persistCounter();
  return out;
}

// ---------- transport ----------
void bufferReading(const String &json) {
  ring[(ringHead + ringCount) % BUFFER_SLOTS] = json;
  if (ringCount < BUFFER_SLOTS) ringCount++;
  else ringHead = (ringHead + 1) % BUFFER_SLOTS;  // full: oldest reading is dropped
}

bool sendHttps(const String &json) {
  if (!cfg.apiUrl.length()) return false;
  HTTPClient http;
  bool secure = cfg.apiUrl.startsWith("https://");
  if (secure) {
    if (!cfg.caPem.length()) { Serial.println("https needs ca_pem (refusing to skip certificate checks)"); return false; }
    tlsClient.setCACert(cfg.caPem.c_str());
    if (!http.begin(tlsClient, cfg.apiUrl + "/api/v1/devices/telemetry")) return false;
  } else if (!http.begin(plainClient, cfg.apiUrl + "/api/v1/devices/telemetry")) return false;
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", "Device " + cfg.deviceId + ":" + cfg.deviceKey);
  int code = http.POST(json);
  http.end();
  return code == 200;  // 4xx means the server rejected it: do not retry forever
}

void publishStatus(JsonDocument &doc) {
  String out;
  serializeJson(doc, out);
  mqtt.publish((topicBase + "/status").c_str(), out.c_str());
}

void onCommand(char *topic, byte *payload, unsigned int len) {
  JsonDocument cmd;
  if (deserializeJson(cmd, payload, len)) return;
  String name = cmd["command"] | "";
  JsonDocument reply;
  reply["command"] = name;
  if (name == "tare") {
    scale.tare(10);
    cfg.scaleOffset = scale.get_offset();
    saveConfig();
    reply["type"] = "calibration_result";
    reply["result"] = "pass";
    reply["offset"] = cfg.scaleOffset;
  } else if (name == "calibrate") {
    float known = cmd["known_mass_kg"] | 0.0f;
    reply["type"] = "calibration_result";
    reply["reference_mass_kg"] = known;
    long raw = scale.read_average(15) - scale.get_offset();
    if (known > 0 && raw != 0) {
      cfg.scaleFactor = raw / known;
      scale.set_scale(cfg.scaleFactor);
      saveConfig();
      reply["result"] = "pass";
      reply["scale_factor"] = cfg.scaleFactor;
    } else reply["result"] = "fail";
  } else if (name == "set_interval") {
    cfg.intervalS = max(10, (int)(cmd["interval_s"] | 300));
    saveConfig();
    reply["type"] = "command_ack";
    reply["result"] = "pass";
  } else if (name == "ping") {
    reply["type"] = "command_ack";
    reply["result"] = "pass";
    reply["status"] = "online";
  } else if (name == "reboot") {
    reply["type"] = "command_ack";
    reply["result"] = "pass";
    publishStatus(reply);
    delay(500);
    ESP.restart();
  } else return;
  publishStatus(reply);
}

bool ensureMqtt() {
  if (mqtt.connected()) return true;
  if (millis() - lastConnectTryMs < 5000) return false;
  lastConnectTryMs = millis();
  if (cfg.mqttPort == 8883) {
    if (!cfg.caPem.length()) return false;
    tlsClient.setCACert(cfg.caPem.c_str());
    mqtt.setClient(tlsClient);
  } else mqtt.setClient(plainClient);
  mqtt.setServer(cfg.mqttHost.c_str(), cfg.mqttPort);
  mqtt.setBufferSize(768);
  mqtt.setCallback(onCommand);
  String will = (topicBase + "/status");
  if (!mqtt.connect(cfg.deviceId.c_str(), cfg.deviceId.c_str(), cfg.deviceKey.c_str(), will.c_str(), 1, true, "{\"status\":\"offline\"}")) {
    Serial.printf("mqtt connect failed, state=%d\n", mqtt.state());
    return false;
  }
  mqtt.subscribe((topicBase + "/commands").c_str(), 1);
  mqtt.publish(will.c_str(), "{\"status\":\"online\",\"firmware_version\":\"" FIRMWARE_VERSION "\"}", true);
  Serial.println("mqtt connected");
  return true;
}

bool sendOne(const String &json) {
  if (cfg.transport == "https") return sendHttps(json);
  return ensureMqtt() && mqtt.publish((topicBase + "/telemetry").c_str(), json.c_str());
}

void flushBuffer() {
  while (ringCount > 0 && sendOne(ring[ringHead])) {
    ring[ringHead] = "";
    ringHead = (ringHead + 1) % BUFFER_SLOTS;
    ringCount--;
  }
}

// ---------- main ----------
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\nPlasticLoop node " FIRMWARE_VERSION " - type 'help'");
  loadConfig();
  pinMode(PIN_US_TRIG, OUTPUT);
  pinMode(PIN_US_ECHO, INPUT);
  analogSetPinAttenuation(PIN_BATTERY, ADC_11db);
  scale.begin(PIN_HX711_DOUT, PIN_HX711_SCK);
  scale.set_offset(cfg.scaleOffset);
  if (cfg.scaleFactor != 0) scale.set_scale(cfg.scaleFactor);
  if (!configured()) {
    Serial.println("Not provisioned. Use 'set ...' then 'save' and 'reboot'.");
    return;
  }
  topicBase = "plasticloop/devices/" + cfg.deviceId;
  WiFi.mode(WIFI_STA);
  WiFi.begin(cfg.wifiSsid.c_str(), cfg.wifiPass.c_str());
  configTime(0, 0, "pool.ntp.org", "time.google.com");
}

void loop() {
  pollSerial();
  if (!configured()) { delay(50); return; }
  if (WiFi.status() == WL_CONNECTED && cfg.transport == "mqtt") {
    if (ensureMqtt()) mqtt.loop();
  }
  if (millis() - lastSendMs >= cfg.intervalS * 1000UL || lastSendMs == 0) {
    if (!clockValid()) { delay(200); return; }  // never send readings with a wrong timestamp
    lastSendMs = millis();
    String reading = buildReading();
    bool online = WiFi.status() == WL_CONNECTED;
    if (online) flushBuffer();
    if (!online || ringCount > 0 || !sendOne(reading)) bufferReading(reading);
    Serial.println(reading);
  }
  delay(20);
}
