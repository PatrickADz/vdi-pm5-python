"""
(C) 2025 by Patricio.

NOTES:
This driver allows communication with a VDI Erickson PM5 power meter
using USB communication.

version 1.2 Sept 2026
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Iterator, Optional

import serial
import serial.tools.list_ports

from . import protocol as proto
from .exceptions import PM5CommunicationError, PM5ConnectionError, PM5PortNotFoundError

logger = logging.getLogger(__name__)


@dataclass
class PowerReading:
    watts: float
    dbm: float
    range_code: Optional[int]
    auto_range: bool
    cal_factor_db: float
    raw_counts: int


class PM5:
    """Serial driver for the VDI Erickson PM5 (USB/FTDI, exposed as a virtual COM port)."""

    DEFAULT_BAUDRATE = 115200
    DEFAULT_TIMEOUT = 1.0  # seconds

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
        target_serial: str = "347VA",
        target_manufacturer: str = "FTDI",
        auto_connect: bool = True,
    ):
        self.baudrate = baudrate
        self.timeout = timeout
        self.target_serial = target_serial
        self.target_manufacturer = target_manufacturer
        self._ser: Optional[serial.Serial] = None

        self.port = port or self.find_port()
        if not self.port:
            raise PM5PortNotFoundError(
                "No port was provided and the PM5 could not be autodetected. "
                "Pass `port=...` explicitly."
            )
        if auto_connect:
            self.connect()

    def find_port(self) -> Optional[str]:
        """Find the port by FTDI serial number/manufacturer (see __init__)."""
        for p in serial.tools.list_ports.comports():
            if p.serial_number == self.target_serial and p.manufacturer and self.target_manufacturer in p.manufacturer:
                logger.info("PM5 autodetected on %s (S/N %s)", p.device, p.serial_number)
                return p.device
        return None

    def connect(self) -> None:
        try:
            self._ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        except Exception as exc:
            raise PM5ConnectionError(f"Could not open {self.port}: {exc}") from exc
        logger.info("Connected to the PM5 on %s", self.port)

    def disconnect(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()
            logger.info("Disconnected from the PM5")

    def __enter__(self) -> "PM5":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()

    @property
    def is_connected(self) -> bool:
        return bool(self._ser and self._ser.is_open)

    def _ensure_connected(self) -> None:
        if not self.is_connected:
            raise PM5ConnectionError("Not connected to the PM5. Call connect() first.")

    def _send(self, command: bytes) -> None:
        self._ensure_connected()
        self._ser.reset_input_buffer()
        self._ser.write(command)

    def _read_ack(self) -> None:
        ack = self._ser.read(1)
        if ack != proto.ACK:
            raise PM5CommunicationError(f"Expected ACK, received {ack!r}")

    def _read_d_response(self) -> tuple[int, int, int, int]:
        """Read the 6-byte 'D...' response and return (countvalue, s1, s2, s3)."""
        resp = self._ser.read(6)
        if len(resp) != 6 or resp[0:1] != b"D":
            raise PM5CommunicationError(f"Unexpected or incomplete response: {resp!r}")
        countvalue = int.from_bytes(resp[1:3], byteorder="little", signed=True)
        return countvalue, resp[3], resp[4], resp[5]

    def zero(self) -> None:
        """Zero the display for the current range (same as the panel Zero button)."""
        self._send(proto.build_command(proto.SYNC_SET, *proto.SET_ZERO))
        self._read_ack()

    def calibrate(self) -> None:
        """Set calibration for the current range (heater at mid-range and stable)."""
        self._send(proto.build_command(proto.SYNC_SET, *proto.SET_CALIBRATE))
        self._read_ack()

    def set_range(self, range_code: int, range_hold: bool = False) -> None:
        """Set the range. It only takes effect if the physical switch is on 'Remote'.

        range_code: one of protocol.RANGE_* (1-4 fixed, 5-8 auto).
        range_hold: for *_AUTO codes, keep that range if set to hold.
        """
        if range_code not in proto.SET_RANGE:
            raise ValueError(f"Invalid range code: {range_code}")
        data = bytes([1 if range_hold else 0, 0, 0, 0])
        self._send(proto.build_command(proto.SYNC_SET, *proto.SET_RANGE[range_code], data=data))
        self._read_ack()

    def set_cal_heater(self, level: int) -> None:
        """Set the internal calibration heater (ignored if the rear switch is in OFF)."""
        if level not in proto.SET_CAL_HEATER:
            raise ValueError(f"Invalid cal heater level: {level}")
        self._send(proto.build_command(proto.SYNC_SET, *proto.SET_CAL_HEATER[level]))
        self._read_ack()

    # query
    def get_power(self) -> PowerReading:
        """Request and decode one power sample ('?D1')."""
        self._send(proto.build_command(proto.SYNC_QUERY, *proto.QUERY_ONE_SAMPLE))
        self._read_ack()
        countvalue, s1, s2, s3 = self._read_d_response()
        status = proto.parse_status(s1, s2, s3)
        if not isinstance(status.range_selected, int):
            raise PM5CommunicationError(
                f"The PM5 did not report a valid range (status3 range field: {status.range_selected!r})"
            )
        watts = proto.counts_to_watts(countvalue, status.range_selected, status.cal_factor_db)
        dbm = 10 * math.log10(watts * 1000) if watts > 0 else float("-inf")
        return PowerReading(
            watts=watts,
            dbm=dbm,
            range_code=status.range_selected,
            auto_range=status.auto_range,
            cal_factor_db=status.cal_factor_db,
            raw_counts=countvalue,
        )

    def get_firmware_version(self) -> str:
        self._send(proto.build_command(proto.SYNC_QUERY, *proto.QUERY_FIRMWARE))
        self._read_ack()
        resp = self._ser.read(6)
        if len(resp) != 6 or resp[0:2] != b"VC":
            raise PM5CommunicationError(f"Unexpected firmware response: {resp!r}")
        main = f"{resp[3]}.{resp[2]}"
        secondary = f"{resp[5]}.{resp[4]}"
        return f"{main} (secondary {secondary})"

    def get_power_high_res(self) -> float:
        """High-resolution power query (returns mW as ASCII exponential text)."""
        self._ensure_connected()
        self._ser.reset_input_buffer()
        self._ser.write(proto.HIGH_RES_QUERY)
        resp = self._ser.read(14)
        if len(resp) != 14:
            raise PM5CommunicationError(f"Expected 14 bytes, received {len(resp)}: {resp!r}")
        if resp[0] != proto.HIGH_RES_OK:
            raise PM5CommunicationError("The PM5 reported a communication error (high-resolution query)")
        return float(resp[1:].decode("ascii").strip())

    def stream_power(self, n: Optional[int] = None, poll_interval: float = 0.0) -> Iterator[PowerReading]:
        """Generator that polls '?D1' repeatedly and yields PowerReading objects."""
        count = 0
        while n is None or count < n:
            yield self.get_power()
            count += 1
            if poll_interval:
                time.sleep(poll_interval)
