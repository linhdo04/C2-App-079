# Arduino BLE telemetry for ESP32 node and ESP32-S3 gateway

This folder converts the ESP-IDF BLE ideas in `bluetooth/ble_get_started/bluedroid`
into an Arduino-framework implementation for your project.

## Why BLE

`ESP32-S3` does not support Bluetooth Classic, so the common protocol between
`ESP32 DevKit V1` and `ESP32-S3` is BLE GATT.

## Architecture

- `ESP32 DevKit V1`:
  BLE peripheral / IoT node
- `ESP32-S3`:
  BLE central / mobile gateway
- Transport:
  custom BLE service with one telemetry characteristic (`READ + NOTIFY`)

The node reads `DHT11` on `GPIO4`, following the same pattern already used in
`client/src/main.cpp`. If the sensor read fails, the node falls back to
simulated telemetry so you can still test the BLE link.

## BLE packet

The characteristic sends a compact binary packet to stay within a single BLE
notification:

- `version`:
  protocol version
- `flags`:
  bit 0 = simulated data, bit 1 = sensor read OK
- `sequence`:
  incrementing sample counter
- `temperature_c_x100`:
  temperature in Celsius multiplied by 100
- `humidity_percent_x100`:
  humidity in percent multiplied by 100
- `uptime_seconds`:
  node uptime

The gateway decodes the packet and forwards a JSON body compatible with your
backend endpoint `POST /api/drones/telemetry`.

## Build with PlatformIO

```powershell
cd bluetooth\arduino_ble_telemetry
pio run -e esp32devkit-v1-node
pio run -e esp32-s3-gateway
```

## Flash and monitor

```powershell
cd bluetooth\arduino_ble_telemetry
pio run -e esp32devkit-v1-node -t upload -t monitor
pio run -e esp32-s3-gateway -t upload -t monitor
```

## Notes

- Default node board:
  `esp32doit-devkit-v1`
- Default gateway board:
  `esp32-s3-devkitc-1`
- If your S3 board variant is different, update `board = ...` in
  `platformio.ini`.
- The gateway now forwards telemetry to `POST /api/drones/telemetry` over
  Wi-Fi using the `X-API-Key` header.
- Update these constants in `src/gateway_main.cpp` before flashing the
  gateway:
  - `kWifiSsid`
  - `kWifiPassword`
  - `kTelemetryEndpoint`
  - `kNodeSerialNumber`
  - `kNodeApiKey`
- Generate `kNodeApiKey` once from your backend using
  `POST /api/drones/nodes/{iot_node_id}/api-key`, then paste the returned
  plaintext key into the gateway firmware. The backend only stores the hash,
  so the plaintext key is shown once.
- The gateway sends payloads in this shape:
  `{"serial_number":"DRONE-001","temperature_celsius":25.8,"humidity_percent":50.0,"data":{"ble_device_name":"UAV-IOT-NODE-01","sequence":7,"uptime_seconds":31,"source":"sensor","sensor_ok":true}}`
