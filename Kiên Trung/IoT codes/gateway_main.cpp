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
#include "lwip/dns.h"

namespace {

constexpr uint32_t kScanDurationSeconds = 5;
constexpr esp_power_level_t kBleTxPower = ESP_PWR_LVL_P9;

// ---- Wi-Fi / backend configuration (fill these in) -------------------------
constexpr char kWifiSsid[] = "Galaxy A50C71E";
constexpr char kWifiPassword[] = "123456789";
// Telemetry ingest endpoint (FastAPI: POST /api/drones/telemetry).
constexpr char kTelemetryUrl[] =
    "https://api.docker-linhdt.site/api/drones/telemetry";
// Per-node API key minted via POST /api/drones/nodes/{iot_node_id}/api-key.
// Sent as the X-API-Key header.
constexpr char kApiKey[] = "drn_c-pgTpraxjPRBJnzU9YMokA_AJNXzD3O6849wD9RjGs";
// Registered serial_number of this node in the backend (the backend resolves
// telemetry to the node by this). Update when the real drone serial is known.
constexpr char kSerialNumber[] = "DEMO-ENV-001";
constexpr uint32_t kWifiConnectTimeoutMs = 15000;
constexpr uint16_t kHttpTimeoutMs = 8000;

BLEAdvertisedDevice *targetDevice = nullptr;
BLEClient *bleClient = nullptr;
BLERemoteCharacteristic *remoteTelemetryCharacteristic = nullptr;
bool shouldConnect = false;
bool connected = false;
uint32_t scanAttempt = 0;

// The latest telemetry packet handed off from the BLE notify callback (which
// runs in the small-stack Bluetooth task) to loop(), which performs the HTTPS
// POST in the main task. Doing TLS in the callback overflows the BTC stack.
portMUX_TYPE telemetryMux = portMUX_INITIALIZER_UNLOCKED;
volatile bool telemetryPending = false;
uav_ble::TelemetryPacket pendingPacket{};

void queueTelemetry(const uav_ble::TelemetryPacket &packet) {
  portENTER_CRITICAL(&telemetryMux);
  pendingPacket = packet;
  telemetryPending = true;
  portEXIT_CRITICAL(&telemetryMux);
}

bool takeTelemetry(uav_ble::TelemetryPacket &out) {
  bool has = false;
  portENTER_CRITICAL(&telemetryMux);
  if (telemetryPending) {
    out = pendingPacket;
    telemetryPending = false;
    has = true;
  }
  portEXIT_CRITICAL(&telemetryMux);
  return has;
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

void ensureWifiConnected() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  Serial.printf("Connecting to Wi-Fi SSID \"%s\"...\n", kWifiSsid);
  WiFi.mode(WIFI_STA);
  WiFi.begin(kWifiSsid, kWifiPassword);

  const uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED &&
         millis() - start < kWifiConnectTimeoutMs) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    // Phone hotspots often hand out a DNS server the ESP32 can't reach, which
    // makes hostByName() fail. Force public resolvers (Google + Cloudflare).
    ip_addr_t dns0;
    ip_addr_t dns1;
    IP_ADDR4(&dns0, 8, 8, 8, 8);
    IP_ADDR4(&dns1, 1, 1, 1, 1);
    dns_setserver(0, &dns0);
    dns_setserver(1, &dns1);

    Serial.print("Wi-Fi connected, IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Wi-Fi connection failed (will retry on next telemetry).");
  }
}

bool postTelemetry(const char *payload) {
  ensureWifiConnected();
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  WiFiClientSecure client;
  // TODO: replace with client.setCACert(rootCa) to validate the server cert in
  // production. setInsecure() skips validation so the POST works immediately.
  client.setInsecure();

  HTTPClient http;
  if (!http.begin(client, kTelemetryUrl)) {
    Serial.println("HTTP begin failed.");
    return false;
  }
  http.setTimeout(kHttpTimeoutMs);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", kApiKey);

  const int status = http.POST(String(payload));
  bool ok = false;
  if (status > 0) {
    Serial.printf("POST %s -> HTTP %d\n", kTelemetryUrl, status);
    const String response = http.getString();
    if (response.length() > 0) {
      Serial.printf("Response: %s\n", response.c_str());
    }
    ok = status >= 200 && status < 300;
  } else {
    Serial.printf("POST failed: %s\n", http.errorToString(status).c_str());
  }

  http.end();
  return ok;
}

// Builds the JSON body and POSTs it. MUST be called from the main task (loop),
// never from the BLE notify callback — TLS needs more stack than the BT task has.
void sendTelemetry(const uav_ble::TelemetryPacket &packet) {
  const float temperature = uav_ble::decodeTemperatureC(packet);
  const float humidity = uav_ble::decodeHumidityPercent(packet);
  const int simulated = uav_ble::isSimulated(packet) ? 1 : 0;

  // Matches the backend DroneTelemetryCreate schema. The node is identified by
  // serial_number; the X-API-Key header also binds the request to a node.
  char payload[224];
  snprintf(payload, sizeof(payload),
           "{\"serial_number\":\"%s\",\"temperature_celsius\":%.2f,"
           "\"humidity_percent\":%.2f,\"data\":{\"simulated\":%d}}",
           kSerialNumber, temperature, humidity, simulated);

  Serial.print("POST /api/drones/telemetry body: ");
  Serial.println(payload);
  postTelemetry(payload);
}

bool decodeAndPrintPacket(const uint8_t *data, size_t length, const char *origin) {
  if (length < sizeof(uav_ble::TelemetryPacket)) {
    Serial.printf("[%s] Invalid payload length: %u\n", origin,
                  static_cast<unsigned int>(length));
    return false;
  }

  uav_ble::TelemetryPacket packet{};
  memcpy(&packet, data, sizeof(packet));

  if (packet.version != uav_ble::kProtocolVersion) {
    Serial.printf("[%s] Unsupported protocol version: %u\n", origin,
                  static_cast<unsigned int>(packet.version));
    return false;
  }

  const float temperature = uav_ble::decodeTemperatureC(packet);
  const float humidity = uav_ble::decodeHumidityPercent(packet);
  const char *source = uav_ble::isSimulated(packet) ? "simulated" : "sensor";

  Serial.printf("[%s] seq=%lu temp=%.2fC hum=%.2f%% uptime=%lus source=%s\n",
                origin, static_cast<unsigned long>(packet.sequence), temperature,
                humidity, static_cast<unsigned long>(packet.uptime_seconds), source);
  // Hand off to loop() for the HTTPS POST; never POST from here (may run in the
  // BLE notify callback / BT task, which has too little stack for TLS).
  queueTelemetry(packet);
  return true;
}

void notifyCallback(BLERemoteCharacteristic *characteristic, uint8_t *data,
                    size_t length, bool isNotify) {
  (void)characteristic;
  decodeAndPrintPacket(data, length, isNotify ? "notify" : "indicate");
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

  if (bleClient == nullptr) {
    bleClient = BLEDevice::createClient();
    bleClient->setClientCallbacks(new GatewayClientCallbacks());
  }

  const String targetAddress = formatAddress(targetDevice->getAddress());
  const int targetRssi = targetDevice->getRSSI();
  const unsigned int targetAddressType =
      static_cast<unsigned int>(targetDevice->getAddressType());

  Serial.printf("Connecting to BLE node at %s (addr_type=%u, rssi=%d)...\n",
                targetAddress.c_str(), targetAddressType, targetRssi);

  const bool didConnect = bleClient->connect(targetDevice);
  clearTargetDevice();

  if (!didConnect) {
    Serial.println("BLE connection failed.");
    return false;
  }

  BLERemoteService *remoteService =
      bleClient->getService(BLEUUID(uav_ble::kTelemetryServiceUuid));
  if (remoteService == nullptr) {
    Serial.println("Telemetry service not found.");
    bleClient->disconnect();
    return false;
  }

  remoteTelemetryCharacteristic =
      remoteService->getCharacteristic(BLEUUID(uav_ble::kTelemetryCharacteristicUuid));
  if (remoteTelemetryCharacteristic == nullptr) {
    Serial.println("Telemetry characteristic not found.");
    bleClient->disconnect();
    return false;
  }

  if (remoteTelemetryCharacteristic->canRead()) {
    const std::string rawValue = remoteTelemetryCharacteristic->readValue();
    decodeAndPrintPacket(
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

  ensureWifiConnected();

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
  if (shouldConnect) {
    shouldConnect = false;
    if (!connectToNode()) {
      Serial.println("Retrying scan after connection failure.");
    }
  }

  uav_ble::TelemetryPacket packet;
  if (takeTelemetry(packet)) {
    sendTelemetry(packet);
  }

  if (!connected && !shouldConnect) {
    scanForNode();
  }

  delay(1000);
}
