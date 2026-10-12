/**
 * @file config.h
 * @brief Configuration definitions for ESP32 and HLK-LD2450 mmWave Radar.
 * 
 * Defines hardware pinouts, baud rates, network parameters, and frame constants.
 */

#pragma once

#include <Arduino.h>

// ============================================================================
// Hardware Pinout Configuration
// ============================================================================
// UART2 connected to HLK-LD2450
#define RADAR_RX_PIN          16   // ESP32 RX2 <- LD2450 TX
#define RADAR_TX_PIN          17   // ESP32 TX2 -> LD2450 RX

// Onboard status LED (ESP32 DevKit usually uses GPIO 2)
#define STATUS_LED_PIN        2

// ============================================================================
// Communication Baud Rates
// ============================================================================
// HLK-LD2450 default baud rate is 256000 bps (8 data bits, 1 stop bit, no parity)
#define RADAR_BAUDRATE        256000

// Serial output to Host PC via USB
#define HOST_SERIAL_BAUDRATE  115200

// ============================================================================
// LD2450 Protocol Constants
// ============================================================================
// Frame structure: Header (4 bytes) + 3 targets * 8 bytes (24 bytes) + Tail (2 bytes) = 30 bytes
#define LD2450_FRAME_LEN      30
#define LD2450_HEADER_BYTE0   0xAA
#define LD2450_HEADER_BYTE1   0xFF
#define LD2450_HEADER_BYTE2   0x03
#define LD2450_HEADER_BYTE3   0x00

#define LD2450_TAIL_BYTE0     0x55
#define LD2450_TAIL_BYTE1     0xCC

#define LD2450_MAX_TARGETS    3

// ============================================================================
// Network / UDP Configuration (Optional Mode)
// ============================================================================
// Set to true to broadcast/stream radar frames over WiFi UDP to host PC
#define ENABLE_WIFI_UDP       false

#define WIFI_SSID             "YOUR_WIFI_SSID"
#define WIFI_PASSWORD         "YOUR_WIFI_PASSWORD"
#define UDP_TARGET_IP         "192.168.1.100" // IP of the PC running the Python backend
#define UDP_TARGET_PORT       8888
