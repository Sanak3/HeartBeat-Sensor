/**
 * @file main.cpp
 * @brief ESP32 firmware for acquiring HLK-LD2450 mmWave radar data and forwarding to Host PC.
 * 
 * Hardware Setup:
 *   - ESP32 DevKit V1
 *   - HLK-LD2450 connected via UART2 (GPIO 16 = RX, GPIO 17 = TX)
 *   - Baudrate: 256000 bps, 8N1
 * 
 * Operation:
 *   1. Synchronizes and reads 30-byte reporting frames from LD2450 radar.
 *   2. Validates frame delimiters (0xAA 0xFF 0x03 0x00 ... 0x55 0xCC).
 *   3. Transmits frames to host via USB Serial (and optionally UDP over WiFi).
 */

#include <Arduino.h>
#include "config.h"

#if ENABLE_WIFI_UDP
#include <WiFi.h>
#include <WiFiUdp.h>

WiFiUDP udp;
#endif

// UART2 instance for communication with the LD2450 radar
HardwareSerial SerialRadar(2);

// Frame buffer and state machine
uint8_t frameBuffer[LD2450_FRAME_LEN];
size_t bufferIndex = 0;
unsigned long lastPacketTime = 0;
unsigned long packetCount = 0;

/**
 * @brief Initializes WiFi connection if UDP mode is enabled in config.h.
 */
void setupNetwork() {
#if ENABLE_WIFI_UDP
    Serial.printf("[WIFI] Connecting to %s", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n[WIFI] Connected!");
        Serial.printf("[WIFI] IP Address: %s\n", WiFi.localIP().toString().c_str());
    } else {
        Serial.println("\n[WIFI] Connection failed. Running in Serial-only mode.");
    }
#endif
}

/**
 * @brief Forward frame to host via USB Serial and/or UDP.
 * 
 * @param buffer Pointer to the 30-byte verified radar frame.
 * @param length Length of the frame (LD2450_FRAME_LEN).
 */
void forwardFrame(const uint8_t* buffer, size_t length) {
    // 1. Forward via USB Serial
    Serial.write(buffer, length);
    Serial.flush();

    // 2. Forward via UDP if enabled and connected
#if ENABLE_WIFI_UDP
    if (WiFi.status() == WL_CONNECTED) {
        udp.beginPacket(UDP_TARGET_IP, UDP_TARGET_PORT);
        udp.write(buffer, length);
        udp.endPacket();
    }
#endif

    packetCount++;
    digitalWrite(STATUS_LED_PIN, (packetCount % 10 < 5) ? HIGH : LOW);
}

void setup() {
    // Initialize status LED
    pinMode(STATUS_LED_PIN, OUTPUT);
    digitalWrite(STATUS_LED_PIN, LOW);

    // Initialize USB Host Serial
    Serial.begin(HOST_SERIAL_BAUDRATE);
    delay(500);

    Serial.println("\n==================================================");
    Serial.println("ESP32 HLK-LD2450 Radar Gateway Initializing");
    Serial.println("==================================================");
    Serial.printf("[RADAR] Opening UART2 on RX: GPIO %d, TX: GPIO %d @ %d bps\n",
                  RADAR_RX_PIN, RADAR_TX_PIN, RADAR_BAUDRATE);

    // Initialize Radar Serial (UART2)
    SerialRadar.begin(RADAR_BAUDRATE, SERIAL_8N1, RADAR_RX_PIN, RADAR_TX_PIN);

    // Optional WiFi setup
    setupNetwork();

    Serial.println("[SYSTEM] Ready. Streaming radar frames...\n");
}

void loop() {
    // Read available bytes from the radar UART
    while (SerialRadar.available() > 0) {
        uint8_t byteIn = SerialRadar.read();

        // Synchronize on frame header: 0xAA, 0xFF, 0x03, 0x00
        if (bufferIndex == 0 && byteIn != LD2450_HEADER_BYTE0) {
            continue;
        }
        if (bufferIndex == 1 && byteIn != LD2450_HEADER_BYTE1) {
            bufferIndex = 0;
            continue;
        }
        if (bufferIndex == 2 && byteIn != LD2450_HEADER_BYTE2) {
            bufferIndex = 0;
            continue;
        }
        if (bufferIndex == 3 && byteIn != LD2450_HEADER_BYTE3) {
            bufferIndex = 0;
            continue;
        }

        // Store valid byte in buffer
        frameBuffer[bufferIndex++] = byteIn;

        // When buffer reaches expected frame size, validate tail and dispatch
        if (bufferIndex == LD2450_FRAME_LEN) {
            if (frameBuffer[LD2450_FRAME_LEN - 2] == LD2450_TAIL_BYTE0 &&
                frameBuffer[LD2450_FRAME_LEN - 1] == LD2450_TAIL_BYTE1) {
                // Valid frame acquired
                forwardFrame(frameBuffer, LD2450_FRAME_LEN);
                lastPacketTime = millis();
            }
            // Reset buffer index for next frame
            bufferIndex = 0;
        }
    }

    // Optional desync watchdog: reset buffer if partial frame has stalled
    if (bufferIndex > 0 && (millis() - lastPacketTime > 100)) {
        bufferIndex = 0;
    }
}
