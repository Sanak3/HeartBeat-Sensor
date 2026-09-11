"""
HLK-LD2450 mmWave Radar Binary Protocol Parser.

This module is responsible for decoding continuous reporting frames emitted
by the Hi-Link HLK-LD2450 24GHz radar sensor.

Protocol Definition:
    Frame Structure (30 bytes):
    - Header (4 bytes):  0xAA 0xFF 0x03 0x00
    - Target 1 (8 bytes): [X_L, X_H, Y_L, Y_H, Speed_L, Speed_H, DistRes_L, DistRes_H]
    - Target 2 (8 bytes): [X_L, X_H, Y_L, Y_H, Speed_L, Speed_H, DistRes_L, DistRes_H]
    - Target 3 (8 bytes): [X_L, X_H, Y_L, Y_H, Speed_L, Speed_H, DistRes_L, DistRes_H]
    - Tail   (2 bytes):  0x55 0xCC

Coordinate Sign Encoding:
    Bit 15 is sign bit (0 = positive / right / moving away, 1 = negative / left / approaching).
    Bits 0-14 denote the magnitude.
"""

from __future__ import annotations

import math
import struct
import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class Target:
    """Represents a single detected spatial target from the LD2450 radar."""
    id: int
    x_mm: int
    y_mm: int
    speed_cms: int
    distance_resolution_mm: int
    is_valid: bool
    distance_mm: float = field(init=False)
    angle_deg: float = field(init=False)

    def __post_init__(self) -> None:
        # Calculate Euclidean distance and azimuth angle relative to sensor origin
        dist = math.hypot(self.x_mm, self.y_mm)
        object.__setattr__(self, "distance_mm", round(dist, 1))
        # 0 deg is directly in front along the +Y axis.
        # Positive angle = right (+X), negative angle = left (-X)
        if self.y_mm != 0 or self.x_mm != 0:
            angle = math.degrees(math.atan2(self.x_mm, self.y_mm))
        else:
            angle = 0.0
        object.__setattr__(self, "angle_deg", round(angle, 1))

    @property
    def x_m(self) -> float:
        """X coordinate in meters."""
        return self.x_mm / 1000.0

    @property
    def y_m(self) -> float:
        """Y coordinate in meters."""
        return self.y_mm / 1000.0

    @property
    def speed_ms(self) -> float:
        """Radial velocity in meters per second."""
        return self.speed_cms / 100.0


@dataclass
class RadarFrame:
    """Represents a single decoded radar report frame containing up to 3 targets."""
    targets: List[Target]
    timestamp: float = field(default_factory=time.time)
    raw_bytes: bytes = b""

    @property
    def valid_targets(self) -> List[Target]:
        """Returns only the actively tracked targets."""
        return [t for t in self.targets if t.is_valid]


class LD2450Parser:
    """Stream parser for extracting and validating LD2450 radar frames."""

    HEADER: bytes = b"\xAA\xFF\x03\x00"
    TAIL: bytes = b"\x55\xCC"
    FRAME_LEN: int = 30
    TARGET_BLOCK_LEN: int = 8
    MAX_TARGETS: int = 3

    def __init__(self) -> None:
        self._buffer = bytearray()

    @staticmethod
    def _decode_sign_magnitude_16(raw_val: int) -> int:
        """
        Decodes a 16-bit integer where MSB (bit 15) is the sign flag.

        Bit 15 == 1 -> negative value
        Bit 15 == 0 -> positive value
        Bits 0-14 -> absolute magnitude
        """
        if raw_val & 0x8000:
            return -(raw_val & 0x7FFF)
        return raw_val & 0x7FFF

    def parse_single_target(self, target_id: int, block: bytes) -> Target:
        """
        Parses an 8-byte target block into a Target object.

        Payload layout (Little-Endian):
            [0:2] -> X coordinate (sign-magnitude)
            [2:4] -> Y coordinate (sign-magnitude)
            [4:6] -> Radial speed (sign-magnitude)
            [6:8] -> Distance resolution (uint16)
        """
        if len(block) != self.TARGET_BLOCK_LEN:
            raise ValueError(f"Target block must be {self.TARGET_BLOCK_LEN} bytes.")

        raw_x, raw_y, raw_speed, raw_res = struct.unpack("<4H", block)

        x_mm = self._decode_sign_magnitude_16(raw_x)
        y_mm = self._decode_sign_magnitude_16(raw_y)
        speed_cms = self._decode_sign_magnitude_16(raw_speed)
        distance_res_mm = raw_res

        # An empty/inactive target typically has all zeros or zero distance resolution
        is_valid = not (x_mm == 0 and y_mm == 0 and speed_cms == 0 and distance_res_mm == 0)

        return Target(
            id=target_id,
            x_mm=x_mm,
            y_mm=y_mm,
            speed_cms=speed_cms,
            distance_resolution_mm=distance_res_mm,
            is_valid=is_valid,
        )

    def parse_frame_payload(self, frame_bytes: bytes) -> Optional[RadarFrame]:
        """
        Validates and parses a full 30-byte frame.
        """
        if len(frame_bytes) != self.FRAME_LEN:
            return None

        if not frame_bytes.startswith(self.HEADER) or not frame_bytes.endswith(self.TAIL):
            return None

        targets: List[Target] = []
        offset = len(self.HEADER)

        for i in range(self.MAX_TARGETS):
            block = frame_bytes[offset : offset + self.TARGET_BLOCK_LEN]
            target = self.parse_single_target(target_id=i + 1, block=block)
            targets.append(target)
            offset += self.TARGET_BLOCK_LEN

        return RadarFrame(targets=targets, raw_bytes=frame_bytes)

    def feed(self, data: bytes) -> List[RadarFrame]:
        """
        Feed incoming streaming bytes from transport.
        Synchronizes frames and returns any complete RadarFrames found.
        """
        self._buffer.extend(data)
        frames: List[RadarFrame] = []

        while len(self._buffer) >= self.FRAME_LEN:
            # Search for header occurrence
            header_idx = self._buffer.find(self.HEADER)
            if header_idx == -1:
                # No header found, keep last 3 bytes in case header was split
                keep_len = len(self.HEADER) - 1
                del self._buffer[:-keep_len]
                break

            # Discard bytes preceding header
            if header_idx > 0:
                del self._buffer[:header_idx]

            # Check if full frame is present
            if len(self._buffer) < self.FRAME_LEN:
                break

            candidate = bytes(self._buffer[: self.FRAME_LEN])

            # Verify trailer
            if candidate.endswith(self.TAIL):
                frame = self.parse_frame_payload(candidate)
                if frame:
                    frames.append(frame)
                del self._buffer[: self.FRAME_LEN]
            else:
                # Corrupted frame or false sync header, skip 1 byte and retry
                del self._buffer[0]

        return frames
