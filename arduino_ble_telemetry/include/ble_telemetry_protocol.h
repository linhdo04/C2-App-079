#pragma once

#include <Arduino.h>
#include <math.h>
#include <stdint.h>

namespace uav_ble {

constexpr char kNodeDeviceName[] = "UAV-IOT-NODE-01";
constexpr char kGatewayDeviceName[] = "UAV-GATEWAY-S3";

constexpr char kTelemetryServiceUuid[] = "7f3b2e10-4b2d-4f8f-a1f0-2c7d9b110001";
constexpr char kTelemetryCharacteristicUuid[] = "7f3b2e10-4b2d-4f8f-a1f0-2c7d9b110002";

constexpr uint8_t kProtocolVersion = 1;
constexpr uint8_t kFlagSimulated = 0x01;
constexpr uint8_t kFlagSensorOk = 0x02;

template <typename T>
inline T clampValue(T value, T min_value, T max_value) {
  return value < min_value ? min_value : (value > max_value ? max_value : value);
}

struct __attribute__((packed)) TelemetryPacket {
  uint8_t version;
  uint8_t flags;
  uint32_t sequence;
  int16_t temperature_c_x100;
  uint16_t humidity_percent_x100;
  uint32_t uptime_seconds;
};

static_assert(sizeof(TelemetryPacket) == 14,
              "TelemetryPacket must fit in a single BLE notification payload");

inline int16_t encodeTemperatureC(float temperature_c) {
  const float clamped = clampValue(temperature_c, -200.0f, 200.0f);
  return static_cast<int16_t>(lroundf(clamped * 100.0f));
}

inline uint16_t encodeHumidityPercent(float humidity_percent) {
  const float clamped = clampValue(humidity_percent, 0.0f, 100.0f);
  return static_cast<uint16_t>(lroundf(clamped * 100.0f));
}

inline float decodeTemperatureC(const TelemetryPacket &packet) {
  return static_cast<float>(packet.temperature_c_x100) / 100.0f;
}

inline float decodeHumidityPercent(const TelemetryPacket &packet) {
  return static_cast<float>(packet.humidity_percent_x100) / 100.0f;
}

inline bool isSimulated(const TelemetryPacket &packet) {
  return (packet.flags & kFlagSimulated) != 0;
}

inline bool sensorOk(const TelemetryPacket &packet) {
  return (packet.flags & kFlagSensorOk) != 0;
}

}  // namespace uav_ble
