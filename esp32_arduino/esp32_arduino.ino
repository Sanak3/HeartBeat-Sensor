/**
 * @file esp32_arduino.ino
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
 * @brief Decodes 16-bit sign-magnitude integer from HLK-LD2450.
 * Bit 15 is sign (1 = negative, 0 = positive), bits 0-14 are magnitude.
 */
int16_t decodeSignMagnitude(uint16_t val) {
    int16_t mag = val & 0x7FFF;
    return (val & 0x8000) ? -mag : mag;
}

/**
 * @brief Forward frame to host via USB Serial and/or UDP.
 * 
 * @param buffer Pointer to the 30-byte verified radar frame.
 * @param length Length of the frame (LD2450_FRAME_LEN).
 */
void forwardFrame(const uint8_t* buffer, size_t length) {
#if DEBUG_SERIAL_READABLE
    // Modo Legível para Serial Monitor da IDE do Arduino
    Serial.printf("\n--- Frame #%lu ---\n", packetCount + 1);
    Serial.print("HEX: ");
    for (size_t i = 0; i < length; i++) {
        if (buffer[i] < 0x10) Serial.print("0");
        Serial.print(buffer[i], HEX);
        Serial.print(" ");
    }
    Serial.println();

    // Decodifica até 3 alvos (cada alvo tem 8 bytes, a partir do byte 4)
    for (int t = 0; t < LD2450_MAX_TARGETS; t++) {
        int offset = 4 + (t * 8);
        uint16_t raw_x = buffer[offset] | (buffer[offset + 1] << 8);
        uint16_t raw_y = buffer[offset + 2] | (buffer[offset + 3] << 8);
        uint16_t raw_spd = buffer[offset + 4] | (buffer[offset + 5] << 8);
        uint16_t dist_res = buffer[offset + 6] | (buffer[offset + 7] << 8);

        int16_t x = decodeSignMagnitude(raw_x);
        int16_t y = decodeSignMagnitude(raw_y);
        int16_t spd = decodeSignMagnitude(raw_spd);

        if (x != 0 || y != 0 || spd != 0) {
            Serial.printf("  [Alvo %d] X: %5d mm | Y: %5d mm | Vel: %3d cm/s | Res: %d mm\n",
                          t + 1, x, y, spd, dist_res);
        } else {
            Serial.printf("  [Alvo %d] Sem deteccao\n", t + 1);
        }
    }
#else
    // 1. Forward via USB Serial (Modo binário bruto para o script Python)
    Serial.write(buffer, length);
    Serial.flush();
#endif

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

#if DEBUG_SERIAL_READABLE
    Serial.println("\n==================================================");
    Serial.println("ESP32 HLK-LD2450 Radar Gateway Initializing");
    Serial.println("==================================================");
    Serial.printf("[RADAR] Opening UART2 on RX: GPIO %d, TX: GPIO %d @ %d bps\n",
                  RADAR_RX_PIN, RADAR_TX_PIN, RADAR_BAUDRATE);
#endif

    // Initialize Radar Serial (UART2)
    SerialRadar.begin(RADAR_BAUDRATE, SERIAL_8N1, RADAR_RX_PIN, RADAR_TX_PIN);

    // Optional WiFi setup
    setupNetwork();

#if DEBUG_SERIAL_READABLE
    Serial.println("[SYSTEM] Ready. Streaming radar frames...\n");
#endif
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
