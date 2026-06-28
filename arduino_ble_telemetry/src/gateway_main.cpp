#include <Arduino.h>
#include <BLEAdvertisedDevice.h>
#include <BLEClient.h>
#include <BLEDevice.h>
#include <BLERemoteCharacteristic.h>
#include <BLERemoteService.h>
#include <BLEScan.h>
#include <BLEUtils.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <string>
#include <string.h>

#include "ble_telemetry_protocol.h"

namespace {

constexpr uint32_t kScanDurationSeconds = 5;
constexpr esp_power_level_t kBleTxPower = ESP_PWR_LVL_P9;
constexpr uint32_t kWiFiReconnectIntervalMs = 10000;
constexpr uint32_t kWiFiConnectTimeoutMs = 15000;
constexpr uint32_t kUploadRetryIntervalMs = 5000;
constexpr uint32_t kConnectPreparationDelayMs = 250;
constexpr bool kVerboseBleScanLogging = true;

constexpr char kWifiSsid[] = "YOUR_WIFI_SSID";
constexpr char kWifiPassword[] = "YOUR_WIFI_PASSWORD";
constexpr char kTelemetryEndpoint[] =
    "https://your-server.example.com/api/drones/telemetry";
constexpr char kNodeSerialNumber[] = "DRONE-001";
constexpr char kNodeApiKey[] = "drn_replace_with_generated_api_key";

BLEAdvertisedDevice *targetDevice = nullptr;
BLEClient *bleClient = nullptr;
BLERemoteCharacteristic *remoteTelemetryCharacteristic = nullptr;
bool shouldConnect = false;
bool connected = false;
uint32_t scanAttempt = 0;
uav_ble::TelemetryPacket pendingPacket{};
bool hasPendingPacket = false;
bool hasLastReceivedPacket = false;
uav_ble::TelemetryPacket lastReceivedPacket{};
unsigned long lastWiFiConnectAttemptMs = 0;
unsigned long lastUploadAttemptMs = 0;

bool hasPlaceholderConfig() {
  return strcmp(kWifiSsid, "YOUR_WIFI_SSID") == 0 ||
         strcmp(kTelemetryEndpoint,
                "https://your-server.example.com/api/drones/telemetry") == 0 ||
         strcmp(kNodeApiKey, "drn_replace_with_generated_api_key") == 0;
}

bool httpUploadEnabled() {
  return !hasPlaceholderConfig();
}

String formatAddress(BLEAddress address) {
  return String(address.toString().c_str());
}

void clearTargetDevice() {
  if (targetDevice != nullptr) {
    delete targetDevice;
    targetDevice = nullptr;
  }
}

void resetBleClient() {
  if (bleClient == nullptr) {
    return;
  }

  if (bleClient->isConnected()) {
    bleClient->disconnect();
    delay(100);
  }

  delete bleClient;
  bleClient = nullptr;
  remoteTelemetryCharacteristic = nullptr;
}

String buildTelemetryJson(const uav_ble::TelemetryPacket &packet) {
  const float temperature = uav_ble::decodeTemperatureC(packet);
  const float humidity = uav_ble::decodeHumidityPercent(packet);
  const char *source = uav_ble::isSimulated(packet) ? "simulated" : "sensor";
  const char *sensorOk = uav_ble::sensorOk(packet) ? "true" : "false";

  char payload[320];
  snprintf(payload, sizeof(payload),
           "{\"serial_number\":\"%s\",\"temperature_celsius\":%.2f,"
           "\"humidity_percent\":%.2f,\"data\":{\"ble_device_name\":\"%s\","
           "\"sequence\":%lu,\"uptime_seconds\":%lu,\"source\":\"%s\","
           "\"sensor_ok\":%s}}",
           kNodeSerialNumber, temperature, humidity, uav_ble::kNodeDeviceName,
           static_cast<unsigned long>(packet.sequence),
           static_cast<unsigned long>(packet.uptime_seconds), source, sensorOk);

  return String(payload);
}

void printServerCompatibleJson(const uav_ble::TelemetryPacket &packet) {
  const String payload = buildTelemetryJson(packet);
  Serial.print("POST /api/drones/telemetry body: ");
  Serial.println(payload);
}

bool isDuplicatePacket(const uav_ble::TelemetryPacket &packet) {
  return hasLastReceivedPacket &&
         packet.sequence == lastReceivedPacket.sequence &&
         packet.uptime_seconds == lastReceivedPacket.uptime_seconds;
}

bool decodePacket(const uint8_t *data, size_t length, uav_ble::TelemetryPacket *packet,
                  const char *origin) {
  if (length < sizeof(uav_ble::TelemetryPacket)) {
    Serial.printf("[%s] Invalid payload length: %u\n", origin,
                  static_cast<unsigned int>(length));
    return false;
  }

  memcpy(packet, data, sizeof(*packet));

  if (packet->version != uav_ble::kProtocolVersion) {
    Serial.printf("[%s] Unsupported protocol version: %u\n", origin,
                  static_cast<unsigned int>(packet->version));
    return false;
  }
  return true;
}

bool decodeAndQueuePacket(const uint8_t *data, size_t length, const char *origin) {
  uav_ble::TelemetryPacket packet{};
  if (!decodePacket(data, length, &packet, origin)) {
    return false;
  }

  const float temperature = uav_ble::decodeTemperatureC(packet);
  const float humidity = uav_ble::decodeHumidityPercent(packet);
  const char *source = uav_ble::isSimulated(packet) ? "simulated" : "sensor";

  Serial.printf("[%s] seq=%lu temp=%.2fC hum=%.2f%% uptime=%lus source=%s\n",
                origin, static_cast<unsigned long>(packet.sequence), temperature,
                humidity, static_cast<unsigned long>(packet.uptime_seconds), source);
  if (isDuplicatePacket(packet)) {
    Serial.println("Duplicate telemetry packet ignored.");
    return true;
  }

  lastReceivedPacket = packet;
  hasLastReceivedPacket = true;
  pendingPacket = packet;
  hasPendingPacket = true;
  printServerCompatibleJson(packet);
  Serial.printf("Queued telemetry seq=%lu for HTTP upload.\n",
                static_cast<unsigned long>(packet.sequence));
  return true;
}

void notifyCallback(BLERemoteCharacteristic *characteristic, uint8_t *data,
                    size_t length, bool isNotify) {
  (void)characteristic;
  decodeAndQueuePacket(data, length, isNotify ? "notify" : "indicate");
}

bool ensureWiFiConnected() {
  if (!httpUploadEnabled()) {
    return false;
  }

  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  const unsigned long now = millis();
  if (now - lastWiFiConnectAttemptMs < kWiFiReconnectIntervalMs) {
    return false;
  }
  lastWiFiConnectAttemptMs = now;

  Serial.printf("Connecting to Wi-Fi SSID \"%s\"...\n", kWifiSsid);
  WiFi.mode(WIFI_STA);
  WiFi.begin(kWifiSsid, kWifiPassword);

  const unsigned long startMs = millis();
  while (WiFi.status() != WL_CONNECTED &&
         millis() - startMs < kWiFiConnectTimeoutMs) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi connection failed. Telemetry will stay queued.");
    return false;
  }

  Serial.print("Wi-Fi connected. IP: ");
  Serial.println(WiFi.localIP());
  return true;
}

bool postTelemetryToServer(const uav_ble::TelemetryPacket &packet) {
  if (!httpUploadEnabled()) {
    return false;
  }

  if (!ensureWiFiConnected()) {
    return false;
  }

  const String payload = buildTelemetryJson(packet);
  HTTPClient http;
  int statusCode = -1;
  String responseBody;

  if (strncmp(kTelemetryEndpoint, "https://", 8) == 0) {
    WiFiClientSecure secureClient;
    secureClient.setInsecure();
    if (!http.begin(secureClient, kTelemetryEndpoint)) {
      Serial.println("Failed to open HTTPS connection to telemetry endpoint.");
      return false;
    }
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-API-Key", kNodeApiKey);
    statusCode = http.POST(reinterpret_cast<const uint8_t *>(payload.c_str()),
                           payload.length());
    responseBody = http.getString();
  } else {
    WiFiClient wifiClient;
    if (!http.begin(wifiClient, kTelemetryEndpoint)) {
      Serial.println("Failed to open HTTP connection to telemetry endpoint.");
      return false;
    }
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-API-Key", kNodeApiKey);
    statusCode = http.POST(reinterpret_cast<const uint8_t *>(payload.c_str()),
                           payload.length());
    responseBody = http.getString();
  }

  http.end();

  if (statusCode <= 0) {
    Serial.printf("Telemetry upload failed: HTTP error %d\n", statusCode);
    return false;
  }

  Serial.printf("Telemetry upload status=%d seq=%lu\n", statusCode,
                static_cast<unsigned long>(packet.sequence));
  if (!responseBody.isEmpty()) {
    Serial.print("Server response: ");
    Serial.println(responseBody);
  }

  if (statusCode < 200 || statusCode >= 300) {
    Serial.println("Server rejected telemetry. Check API key, serial_number, or payload.");
    return false;
  }

  return true;
}

void flushPendingTelemetry() {
  if (!hasPendingPacket) {
    return;
  }

  if (!httpUploadEnabled()) {
    return;
  }

  const unsigned long now = millis();
  if (now - lastUploadAttemptMs < kUploadRetryIntervalMs) {
    return;
  }
  lastUploadAttemptMs = now;

  const uav_ble::TelemetryPacket packet = pendingPacket;
  if (!postTelemetryToServer(packet)) {
    return;
  }

  if (hasPendingPacket && pendingPacket.sequence == packet.sequence) {
    hasPendingPacket = false;
  }
}

class GatewayClientCallbacks : public BLEClientCallbacks {
 public:
  void onConnect(BLEClient *client) override {
    Serial.printf("Connected to BLE node at %s\n",
                  formatAddress(client->getPeerAddress()).c_str());
  }

  void onDisconnect(BLEClient *client) override {
    (void)client;
    connected = false;
    remoteTelemetryCharacteristic = nullptr;
    Serial.println("Disconnected from BLE node. Scanning again...");
  }
};

class NodeAdvertisedDeviceCallbacks : public BLEAdvertisedDeviceCallbacks {
 public:
  void onResult(BLEAdvertisedDevice advertisedDevice) override {
    if (kVerboseBleScanLogging) {
      Serial.printf("BLE seen: %s\n", advertisedDevice.toString().c_str());
    }

    const String deviceName =
        advertisedDevice.haveName() ? advertisedDevice.getName().c_str() : "";
    const bool nameMatch =
        advertisedDevice.haveName() &&
        advertisedDevice.getName() == std::string(uav_ble::kNodeDeviceName);
    const bool serviceMatch =
        advertisedDevice.haveServiceUUID() &&
        advertisedDevice.isAdvertisingService(BLEUUID(uav_ble::kTelemetryServiceUuid));

    if (!nameMatch && !serviceMatch) {
      return;
    }

    Serial.printf(
        "Found target node: addr=%s rssi=%d name=\"%s\" nameMatch=%s "
        "serviceMatch=%s\n",
        formatAddress(advertisedDevice.getAddress()).c_str(),
        advertisedDevice.getRSSI(), deviceName.c_str(),
        nameMatch ? "yes" : "no", serviceMatch ? "yes" : "no");

    BLEDevice::getScan()->stop();

    clearTargetDevice();
    targetDevice = new BLEAdvertisedDevice(advertisedDevice);
    shouldConnect = true;
  }
};

bool connectToNode() {
  if (targetDevice == nullptr) {
    return false;
  }

  resetBleClient();
  bleClient = BLEDevice::createClient();
  bleClient->setClientCallbacks(new GatewayClientCallbacks());

  const String targetAddress = formatAddress(targetDevice->getAddress());
  const int targetRssi = targetDevice->getRSSI();
  const unsigned int targetAddressType =
      static_cast<unsigned int>(targetDevice->getAddressType());

  Serial.printf("Connecting to BLE node at %s (addr_type=%u, rssi=%d)...\n",
                targetAddress.c_str(), targetAddressType, targetRssi);
  delay(kConnectPreparationDelayMs);

  const bool didConnect = bleClient->connect(targetDevice);
  clearTargetDevice();

  if (!didConnect) {
    Serial.println("BLE connection failed.");
    resetBleClient();
    return false;
  }

  BLERemoteService *remoteService =
      bleClient->getService(BLEUUID(uav_ble::kTelemetryServiceUuid));
  if (remoteService == nullptr) {
    Serial.println("Telemetry service not found.");
    resetBleClient();
    return false;
  }

  remoteTelemetryCharacteristic =
      remoteService->getCharacteristic(BLEUUID(uav_ble::kTelemetryCharacteristicUuid));
  if (remoteTelemetryCharacteristic == nullptr) {
    Serial.println("Telemetry characteristic not found.");
    resetBleClient();
    return false;
  }

  if (remoteTelemetryCharacteristic->canRead()) {
    const std::string rawValue = remoteTelemetryCharacteristic->readValue();
    decodeAndQueuePacket(
        reinterpret_cast<const uint8_t *>(rawValue.data()), rawValue.length(), "read");
  }

  if (remoteTelemetryCharacteristic->canNotify()) {
    remoteTelemetryCharacteristic->registerForNotify(notifyCallback);
    Serial.println("Subscribed to telemetry notifications.");
  } else {
    Serial.println("Telemetry characteristic has no notify property.");
  }

  connected = true;
  Serial.println("Gateway is ready to receive telemetry.");
  return true;
}

void scanForNode() {
  BLEScan *scan = BLEDevice::getScan();
  ++scanAttempt;
  Serial.printf("Scanning for BLE node... attempt=%lu\n",
                static_cast<unsigned long>(scanAttempt));
  BLEScanResults results = scan->start(kScanDurationSeconds, false);
  Serial.printf("Scan complete. Devices seen=%d targetPending=%s connected=%s\n",
                results.getCount(), shouldConnect ? "yes" : "no",
                connected ? "yes" : "no");
  scan->clearResults();
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("Starting BLE mobile gateway...");
  if (hasPlaceholderConfig()) {
    Serial.println(
        "Placeholder Wi-Fi/API config detected. BLE receive mode only; HTTP upload disabled.");
  } else {
    ensureWiFiConnected();
  }

  BLEDevice::init(uav_ble::kGatewayDeviceName);
  BLEDevice::setPower(kBleTxPower);

  BLEScan *scan = BLEDevice::getScan();
  scan->setAdvertisedDeviceCallbacks(new NodeAdvertisedDeviceCallbacks());
  scan->setInterval(1349);
  scan->setWindow(449);
  scan->setActiveScan(true);

  Serial.print("Gateway BLE MAC: ");
  Serial.println(BLEDevice::getAddress().toString().c_str());
  Serial.print("Looking for node name: ");
  Serial.println(uav_ble::kNodeDeviceName);
  Serial.print("Looking for service UUID: ");
  Serial.println(uav_ble::kTelemetryServiceUuid);
}

void loop() {
  if (httpUploadEnabled()) {
    ensureWiFiConnected();
  }

  if (shouldConnect) {
    shouldConnect = false;
    if (!connectToNode()) {
      Serial.println("Retrying scan after connection failure.");
    }
  }

  if (!connected && !shouldConnect) {
    scanForNode();
  }

  if (httpUploadEnabled()) {
    flushPendingTelemetry();
  }
  delay(1000);
}
