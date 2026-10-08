# ESP32 integration

Firmware: [`firmware/esp32/plasticloop_node/plasticloop_node.ino`](../firmware/esp32/plasticloop_node/plasticloop_node.ino).
It compiles with arduino-cli (see [TEST_REPORT.md](TEST_REPORT.md)). **It has not yet been run on physical hardware in this
project**; treat the wiring and calibration steps below as the procedure to follow and verify on your bench.

## Bill of materials (one collection point)

| Part | Notes |
|---|---|
| ESP32 DevKit (ESP32-WROOM-32) | 3.3 V logic |
| Load cell (e.g. 50–200 kg platform) + HX711 module | HX711 powered from 3.3 V |
| HC-SR04 ultrasonic sensor | 5 V device: its ECHO pin **must** go through a divider to the ESP32 |
| Li-ion cell + charger/protection board, or 5 V supply | Battery sense through a 100 k / 100 k divider |
| Weatherproof enclosure, cable glands | Keep the ultrasonic face clear and pointing straight down into the bin |

## Wiring

| ESP32 | Connects to |
|---|---|
| GPIO16 | HX711 DOUT |
| GPIO17 | HX711 SCK |
| 3V3 / GND | HX711 VCC / GND |
| GPIO5 | HC-SR04 TRIG |
| GPIO18 | HC-SR04 ECHO **via 1 kΩ (series) + 2 kΩ (to GND) divider** (5 V → 3.3 V) |
| 5V / GND | HC-SR04 VCC / GND |
| GPIO34 | Battery + through 100 kΩ / 100 kΩ divider (ADC input only pin) |

Power precautions: common ground for all modules; keep load-cell wires short and twisted; never feed 5 V into a GPIO;
add a 100 µF capacitor near the ESP32 if Wi-Fi bursts cause brown-outs.

## Register the device

1. Panchayat admin → **Devices → Register device**: device ID (e.g. `DEV-ESP32-010`), collection point, max weight, interval.
2. The app shows the **device key, MQTT username and topics once**. Only hashes are stored on the server. Keep the key safe;
   use **Issue new key** to rotate or **Revoke access** to block the device.

## Provision over USB serial (no credentials in source code)

Flash the sketch, open a serial monitor at 115200 baud, then:

```
set wifi_ssid <network>
set wifi_pass <password>
set device_id DEV-ESP32-010
set device_key <key shown once in the web app>
set mqtt_host <broker IP or hostname>
set mqtt_port 1883            # 8883 for TLS (requires: set ca_pem -----BEGIN CERTIFICATE-----\n...)
set interval_s 300
set bin_depth_cm 90           # distance from sensor face to the bin floor
save
reboot
```

`show` prints the configuration with secrets masked. `factory_reset` wipes NVS. For HTTPS instead of MQTT:
`set transport https` and `set api_url https://your-domain` plus `set ca_pem ...` (the firmware refuses HTTPS without a CA
certificate rather than skipping verification; plain `http://` is accepted for LAN development only).

## Calibrate

1. Empty platform: `tare` (or **Tare** from the device page, which sends an MQTT command).
2. Place a known mass (e.g. a 10 kg reference): `calibrate 10` (or **Calibrate** with the reference mass on the device page).
3. The device reports `calibration_result` on its status topic; the server stores it under **Calibration** and marks the
   device calibrated. Until calibrated, the node reports `weight_kg: null` instead of a guessed value.

## Data contract

Telemetry (`plasticloop/devices/<id>/telemetry` or `POST /api/v1/devices/telemetry` with `Authorization: Device <id>:<key>`):

```json
{"device_id":"DEV-ESP32-010","reading_id":"DEV-ESP32-010-1791500000-42","timestamp":"2026-10-09T07:30:00Z",
 "weight_kg":12.345,"fill_percent":63.5,"battery_percent":81,"sensor_status":"ok","firmware_version":"1.0.0"}
```

* `reading_id` is unique per reading; the server ignores duplicates, so the node can resend safely.
* Readings are only sent once NTP has set the clock; unsent readings stay in a 50-slot RAM buffer and are flushed on reconnect.
* The server flags (but stores) out-of-range weights, negative drift, sensor errors and clock skew; only `ok` readings
  update the bin fill level.

Status (`.../status`): the node publishes `{"status":"online"}` (retained) on connect and registers a last-will
`{"status":"offline"}`. Command results use `{"type":"calibration_result"|"command_ack","command":...,"result":"pass"|"fail",...}`.

Commands (`.../commands`): `{"command":"tare"}`, `{"command":"calibrate","known_mass_kg":10}`,
`{"command":"set_interval","interval_s":600}`, `{"command":"ping"}`, `{"command":"reboot"}`.

## Broker security

`infra/mosquitto/acl`: device user `%u` may write only `plasticloop/devices/%u/telemetry|status` and read only
`.../%u/commands`. Verified against the real broker: a device publishing on another device's topic is dropped, a wrong key
is refused. For internet-facing brokers use TLS on 8883 (see [DEPLOYMENT.md](DEPLOYMENT.md)) and firewall 1883.

## Without hardware

The simulator speaks the same contract (`simulators/iot-device/simulator.py`, MQTT or HTTPS; every payload carries
`"synthetic": true` and simulated devices are always stored as synthetic). The web page **Devices → Device simulator** drives
seeded simulated devices through the same ingestion service.
