"""
Transport Layer for HLK-LD2450 Radar Data Stream.

Provides an abstract Transport interface and concrete implementations for:
  - Serial (USB-UART bridge via PySerial)
  - UDP (Network socket listener)
"""

from __future__ import annotations

import abc
import logging
import socket
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class Transport(abc.ABC):
    """Abstract base class for byte streaming transports."""

    @abc.abstractmethod
    def open(self) -> None:
        """Opens the transport connection."""
        pass

    @abc.abstractmethod
    def close(self) -> None:
        """Closes the transport connection."""
        pass

    @abc.abstractmethod
    def read(self, max_bytes: int = 1024) -> bytes:
        """Reads incoming bytes from the transport."""
        pass

    @property
    @abc.abstractmethod
    def is_open(self) -> bool:
        """Returns True if the transport connection is currently open."""
        pass

    def __enter__(self) -> "Transport":
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


class SerialTransport(Transport):
    """Serial port transport implementation using PySerial."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.5) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: Optional[Any] = None

    def open(self) -> None:
        if self.is_open:
            return

        try:
            import serial  # Lazy import pyserial
        except ImportError:
            raise ImportError(
                "pyserial package is required for SerialTransport. Install with: pip install pyserial"
            )

        logger.info("Opening serial port %s @ %d bps", self.port, self.baudrate)
        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=self.timeout,
        )

    def close(self) -> None:
        if self._serial and self._serial.is_open:
            logger.info("Closing serial port %s", self.port)
            self._serial.close()
        self._serial = None

    def read(self, max_bytes: int = 1024) -> bytes:
        if not self.is_open or self._serial is None:
            return b""

        try:
            waiting = self._serial.in_waiting
            num_to_read = max(1, min(waiting, max_bytes)) if waiting > 0 else 1
            return self._serial.read(num_to_read)
        except Exception as e:
            logger.error("Error reading from serial port: %s", e)
            return b""

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open


class UDPTransport(Transport):
    """UDP socket transport implementation for receiving forwarded frames over WiFi."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8888, timeout: float = 0.5) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None

    def open(self) -> None:
        if self.is_open:
            return

        logger.info("Binding UDP socket to %s:%d", self.host, self.port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(self.timeout)
        sock.bind((self.host, self.port))
        self._sock = sock

    def close(self) -> None:
        if self._sock:
            logger.info("Closing UDP socket on %s:%d", self.host, self.port)
            self._sock.close()
            self._sock = None

    def read(self, max_bytes: int = 1024) -> bytes:
        if not self.is_open or self._sock is None:
            return b""

        try:
            data, _ = self._sock.recvfrom(max_bytes)
            return data
        except socket.timeout:
            return b""
        except Exception as e:
            logger.error("Error reading from UDP socket: %s", e)
            return b""

    @property
    def is_open(self) -> bool:
        return self._sock is not None


def create_transport(config: Dict[str, Any], transport_override: Optional[str] = None) -> Transport:
    """
    Factory function to instantiate the configured transport (Serial or UDP).

    :param config: Dictionary containing transport configuration.
    :param transport_override: Optional CLI override ("serial" or "udp").
    :return: An initialized Transport instance.
    """
    transport_cfg = config.get("transport", {})
    trans_type = transport_override or transport_cfg.get("type", "serial")
    trans_type = trans_type.lower()

    if trans_type == "serial":
        s_cfg = transport_cfg.get("serial", {})
        port = s_cfg.get("port", "/dev/ttyUSB0")
        baud = s_cfg.get("baudrate", 115200)
        timeout = s_cfg.get("timeout", 0.5)
        return SerialTransport(port=port, baudrate=baud, timeout=timeout)

    elif trans_type == "udp":
        u_cfg = transport_cfg.get("udp", {})
        host = u_cfg.get("host", "0.0.0.0")
        port = u_cfg.get("port", 8888)
        return UDPTransport(host=host, port=port)

    else:
        raise ValueError(f"Unsupported transport type: {trans_type}")
