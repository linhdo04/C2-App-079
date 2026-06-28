#include <Arduino.h>
#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <DHT.h>
#include <math.h>

#include "ble_telemetry_protocol.h"

namespace {

constexpr uint8_t kDhtPin = 4;
constexpr uint8_t kDhtType = DHT11;
constexpr uint32_t kPublishIntervalMs = 5000;
constexpr esp_power_level_t kBleTxPower = ESP_PWR_LVL_P9;

struct SensorReading {
  float temperature;
  float humidity;
  bool simulated;
};

DHT dht(kDhtPin, kDhtType);
BLECharacteristic *telemetryCharacteristic = nullptr;
bool gatewayConnected = false;
bool lastGatewayConnectedState = false;
uint32_t sequenceCounter = 0;
unsigned long lastPublishMs = 0;

String formatBleAddress(const uint8_t *address) {
  char buffer[18];
  snprintf(buffer, sizeof(buffer), "%02X:%02X:%02X:%02X:%02X:%02X", address[0],
           address[1], address[2], address[3], address[4], address[5]);
  return String(buffer);
}

SensorReading buildSimulatedReading() {
  const float seconds = millis() / 1000.0f;
  const float temperature =
      30.0f + 4.2f * sinf(seconds / 50.0f) + 0.8f * sinf(seconds / 9.0f);
  const float humidity =
      64.0f + 8.0f * sinf(seconds / 65.0f + 1.2f) - 2.5f * sinf(seconds / 13.0f);

  return {temperature, humidity, true};
}

SensorReading readSensorData() {
  const float temperature = dht.readTemperature();
  const float humidity = dht.readHumidity();

  if (!isnan(temperature) && !isnan(humidity)) {
    return {temperature, humidity, false};
  }

  Serial.println("DHT11 read failed, using simulated values.");
  return buildSimulatedReading();
}

class TelemetryServerCallbacks : public BLEServerCallbacks {
 public:
  void onConnect(BLEServer *server) override {
    (void)server;
    gatewayConnected = true;
  }

  void onConnect(BLEServer *server, esp_ble_gatts_cb_param_t *param) override {
    onConnect(server);
    Serial.printf("Gateway connected from %s (conn_id=%u)\n",
                  formatBleAddress(param->connect.remote_bda).c_str(),
                  static_cast<unsigned int>(param->connect.conn_id));
  }

  void onDisconnect(BLEServer *server) override {
    (void)server;
    gatewayConnected = false;
  }

  void onDisconnect(BLEServer *server,
                    esp_ble_gatts_cb_param_t *param) override {
    onDisconnect(server);
    Serial.printf("Gateway disconnected from %s (reason=%u)\n",
                  formatBleAddress(param->disconnect.remote_bda).c_str(),
                  static_cast<unsigned int>(param->disconnect.reason));
  }
};

void publishTelemetry() {
  const SensorReading reading = readSensorData();

  uav_ble::TelemetryPacket packet{};
  packet.version = uav_ble::kProtocolVersion;
  packet.flags = reading.simulated ? uav_ble::kFlagSimulated : uav_ble::kFlagSensorOk;
  packet.sequence = ++sequenceCounter;
  packet.temperature_c_x100 = uav_ble::encodeTemperatureC(reading.temperature);
  packet.humidity_percent_x100 = uav_ble::encodeHumidityPercent(reading.humidity);
  packet.uptime_seconds = millis() / 1000UL;

  telemetryCharacteristic->setValue(
      reinterpret_cast<uint8_t *>(&packet), sizeof(packet));

  if (gatewayConnected) {
    telemetryCharacteristic->notify();
  }

  Serial.printf("TX seq=%lu temp=%.2fC hum=%.2f%% source=%s connected=%s\n",
                static_cast<unsigned long>(packet.sequence), reading.temperature,
                reading.humidity, reading.simulated ? "simulated" : "sensor",
                gatewayConnected ? "yes" : "no");
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("Starting BLE telemetry node...");
  dht.begin();

  BLEDevice::init(uav_ble::kNodeDeviceName);
  BLEDevice::setPower(kBleTxPower);

  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new TelemetryServerCallbacks());

  BLEService *telemetryService =
      server->createService(uav_ble::kTelemetryServiceUuid);

  telemetryCharacteristic = telemetryService->createCharacteristic(
      uav_ble::kTelemetryCharacteristicUuid,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  telemetryCharacteristic->addDescriptor(new BLE2902());

  uav_ble::TelemetryPacket initialPacket{};
  initialPacket.version = uav_ble::kProtocolVersion;
  telemetryCharacteristic->setValue(
      reinterpret_cast<uint8_t *>(&initialPacket), sizeof(initialPacket));

  telemetryService->start();

  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(uav_ble::kTelemetryServiceUuid);
  advertising->setScanResponse(true);
  advertising->setMinPreferred(0x06);
  advertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();

  Serial.print("Advertising BLE service as ");
  Serial.println(uav_ble::kNodeDeviceName);
  Serial.print("Node BLE MAC: ");
  Serial.println(BLEDevice::getAddress().toString().c_str());
  Serial.print("Telemetry service UUID: ");
  Serial.println(uav_ble::kTelemetryServiceUuid);

  publishTelemetry();
  lastPublishMs = millis();
}

void loop() {
  if (millis() - lastPublishMs >= kPublishIntervalMs) {
    lastPublishMs = millis();
    publishTelemetry();
  }

  if (gatewayConnected != lastGatewayConnectedState) {
    if (gatewayConnected) {
      Serial.println("Gateway session active.");
    } else {
      Serial.println("Gateway disconnected. Restarting advertising.");
      delay(200);
      BLEDevice::startAdvertising();
    }
    lastGatewayConnectedState = gatewayConnected;
  }

  delay(20);
}
