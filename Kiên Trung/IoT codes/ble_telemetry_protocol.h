#ifndef BLE_TELEMETRY_PROTOCOL_H
#define BLE_TELEMETRY_PROTOCOL_H

#include <math.h>
#include <stdint.h>

// Shared BLE telemetry contract between the sensor node (GATT server) and the
// mobile gateway (GATT client). Both firmware images must use an identical
// definition because the packet is exchanged as a raw byte blob.
namespace uav_ble {

// Bump whenever the on-wire TelemetryPacket layout or semantics change.
constexpr uint8_t kProtocolVersion = 1;

// Packet flag bits.
constexpr uint8_t kFlagSensorOk = 0x00;   // Reading came from the DHT sensor.
constexpr uint8_t kFlagSimulated = 0x01;  // Reading was synthetically generated.

// BLE identifiers. The UUIDs are random 128-bit values reserved for this app.
constexpr char kNodeDeviceName[] = "UAV-IOT-NODE-01";
constexpr char kGatewayDeviceName[] = "UAV-GATEWAY-S3";
constexpr char kTelemetryServiceUuid[] = "7f3b2e10-4b2d-4f8f-a1f0-2c7d9b110001";
constexpr char kTelemetryCharacteristicUuid[] = "7f3b2e10-4b2d-4f8f-a1f0-2c7d9b110002";

// Fixed-point scaling factor applied to temperature and humidity values so they
// can be transported as integers.
constexpr float kFixedPointScale = 100.0f;

#pragma pack(push, 1)
struct TelemetryPacket {
  uint8_t version;                // Protocol version (kProtocolVersion).
  uint8_t flags;                  // Bitmask of kFlag* values.
  uint32_t sequence;              // Monotonically increasing message counter.
  int16_t temperature_c_x100;     // Temperature in degrees C * 100.
  uint16_t humidity_percent_x100; // Relative humidity in % * 100.
  uint32_t uptime_seconds;        // Node uptime in seconds.
};
#pragma pack(pop)

inline int16_t encodeTemperatureC(float celsius) {
  return static_cast<int16_t>(lroundf(celsius * kFixedPointScale));
}

inline uint16_t encodeHumidityPercent(float percent) {
  if (percent < 0.0f) {
    percent = 0.0f;
  }
  return static_cast<uint16_t>(lroundf(percent * kFixedPointScale));
}

inline float decodeTemperatureC(const TelemetryPacket &packet) {
  return packet.temperature_c_x100 / kFixedPointScale;
}

inline float decodeHumidityPercent(const TelemetryPacket &packet) {
  return packet.humidity_percent_x100 / kFixedPointScale;
}

inline bool isSimulated(const TelemetryPacket &packet) {
  return (packet.flags & kFlagSimulated) != 0;
}

}  // namespace uav_ble

#endif  // BLE_TELEMETRY_PROTOCOL_H
