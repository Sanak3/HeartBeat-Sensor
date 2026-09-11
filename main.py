#!/usr/bin/env python3
"""
HLK-LD2450 mmWave Radar Spatial Tracking & Presence Detection System.

Main orchestrator script:
  1. Loads configuration from JSON.
  2. Initializes Transport (Serial / UDP / Mock).
  3. Feeds incoming byte stream to LD2450Parser.
  4. Evaluates AABB geofence zones via ZoneManager.
  5. Updates active visualization view (Rich CLI and/or Matplotlib 2D Plot).
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict

from core.ld2450_parser import LD2450Parser, RadarFrame, Target
from core.transport import SerialTransport, Transport, UDPTransport, create_transport
from core.zone_manager import ZoneManager
from views.cli_view import CLIView
from views.plot_view import PlotView

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("RadarMain")


class MockTransport(Transport):
    """
    Mock transport generating synthetic LD2450 binary frames for offline testing
    without physical ESP32/Radar hardware connected.
    """

    def __init__(self, fps: float = 10.0) -> None:
        self.fps = fps
        self._interval = 1.0 / fps
        self._is_open = False
        self._last_frame_time = 0.0
        self._angle = 0.0

    def open(self) -> None:
        self._is_open = True
        logger.info("MockTransport opened. Generating synthetic radar frames @ %.1f FPS.", self.fps)

    def close(self) -> None:
        self._is_open = False
        logger.info("MockTransport closed.")

    @property
    def is_open(self) -> bool:
        return self._is_open

    def _encode_val(self, val: int) -> tuple[int, int]:
        """Encodes sign-magnitude 16-bit integer into two little-endian bytes."""
        sign_bit = 0x8000 if val < 0 else 0x0000
        magnitude = min(abs(val), 0x7FFF)
        raw = magnitude | sign_bit
        return raw & 0xFF, (raw >> 8) & 0xFF

    def read(self, max_bytes: int = 1024) -> bytes:
        if not self._is_open:
            return b""

        now = time.time()
        if now - self._last_frame_time < self._interval:
            time.sleep(0.01)
            return b""

        self._last_frame_time = now
        self._angle += 0.08

        # Target 1: Walking across the desk area in an orbit/oscillation
        t1_x = int(500 * math.sin(self._angle))
        t1_y = int(1400 + 400 * math.cos(self._angle))
        t1_speed = int(35 * math.cos(self._angle))
        t1_res = 120

        # Target 2: Walking toward doorway
        t2_x = int(1600 + 300 * math.sin(self._angle * 0.7))
        t2_y = int(3200 + 600 * math.cos(self._angle * 0.7))
        t2_speed = int(-45 * math.sin(self._angle * 0.7))
        t2_res = 160

        # Build 30-byte frame
        payload = bytearray(b"\xAA\xFF\x03\x00")

        for x, y, spd, res in [(t1_x, t1_y, t1_speed, t1_res), (t2_x, t2_y, t2_speed, t2_res), (0, 0, 0, 0)]:
            xl, xh = self._encode_val(x)
            yl, yh = self._encode_val(y)
            sl, sh = self._encode_val(spd)
            rl, rh = res & 0xFF, (res >> 8) & 0xFF
            payload.extend([xl, xh, yl, yh, sl, sh, rl, rh])

        payload.extend(b"\x55\xCC")
        return bytes(payload)


def load_config(config_path: Path) -> Dict[str, Any]:
    """Loads and validates JSON settings."""
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HLK-LD2450 mmWave Radar Spatial Tracking & Presence Detection System."
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config/settings.json"),
        help="Path to JSON settings file (default: config/settings.json)",
    )
    parser.add_argument(
        "-v",
        "--view",
        choices=["cli", "plot", "both"],
        default="cli",
        help="Visualization mode: 'cli' (terminal dashboard), 'plot' (2D Matplotlib), or 'both'",
    )
    parser.add_argument(
        "-t",
        "--transport",
        choices=["serial", "udp", "mock"],
        default=None,
        help="Transport type override: 'serial', 'udp', or 'mock'",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=str,
        default=None,
        help="Serial port override (e.g. /dev/ttyUSB0 or COM3)",
    )
    parser.add_argument(
        "-b",
        "--baud",
        type=int,
        default=None,
        help="Serial baudrate override (e.g. 115200 or 256000)",
    )

    args = parser.parse_args()

    # Load configuration
    try:
        config = load_config(args.config)
    except Exception as e:
        logger.error("Failed to load configuration: %s", e)
        sys.exit(1)

    # Apply overrides
    if args.port:
        config.setdefault("transport", {}).setdefault("serial", {})["port"] = args.port
    if args.baud:
        config.setdefault("transport", {}).setdefault("serial", {})["baudrate"] = args.baud

    # Setup Spatial Zone Manager
    zone_cfg = config.get("zones", [])
    zone_manager = ZoneManager.from_config(zone_cfg)
    logger.info("Loaded %d spatial zones from configuration.", len(zone_manager.zones))

    # Setup Transport
    if args.transport == "mock":
        transport: Transport = MockTransport(fps=10.0)
    else:
        transport = create_transport(config, transport_override=args.transport)

    # Setup Radar Frame Parser
    ld2450_parser = LD2450Parser()

    # Setup Views
    cli_view: CLIView | None = None
    plot_view: PlotView | None = None

    if args.view in ("cli", "both"):
        cli_view = CLIView(zone_manager=zone_manager)
    if args.view in ("plot", "both"):
        radar_cfg = config.get("radar", {})
        plot_view = PlotView(
            zone_manager=zone_manager,
            max_distance_m=radar_cfg.get("max_distance_mm", 6000) / 1000.0,
            fov_deg=float(radar_cfg.get("fov_degrees", 120)),
        )

    # Signal handling for clean exit
    running = True

    def sig_handler(sig: int, frame: Any) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    # Connect transport and start views
    try:
        transport.open()
    except Exception as e:
        logger.error("Could not open transport: %s", e)
        sys.exit(1)

    if cli_view:
        cli_view.start()

    logger.info("System initialized. Processing radar stream... (Press Ctrl+C to exit)")

    packet_counter = 0
    transport_name = type(transport).__name__

    try:
        while running:
            # Read incoming stream
            raw_bytes = transport.read(1024)
            if not raw_bytes:
                time.sleep(0.005)
                continue

            # Parse incoming bytes into frames
            frames = ld2450_parser.feed(raw_bytes)

            for frame in frames:
                packet_counter += 1
                occupancy = zone_manager.evaluate_occupancy(frame.targets)
                stats = {
                    "transport_type": transport_name,
                    "packet_count": packet_counter,
                }

                if cli_view:
                    cli_view.update(frame, occupancy, stats)

                if plot_view:
                    plot_view.update(frame, occupancy)

    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down radar system...")
        if cli_view:
            cli_view.stop()
        if plot_view:
            plot_view.close()
        transport.close()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    main()
