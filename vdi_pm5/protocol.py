"""Protocol constants and low-level helpers for the VDI Erickson PM5.

Reference: PM5 Operational Manual (VDI, 2019), Appendix One
(Programming Communications and Commands via USB) and Appendix Two
(VDI Power Correction Factors).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

SYNC_SET = b"!"
SYNC_QUERY = b"?"
TERMINATOR = b"\r"
ACK = b"\x06"
NAK = b"\x15"

# Range codes (front panel / remote), Table 1 of the manual.
RANGE_200uW = 1
RANGE_2mW = 2
RANGE_20mW = 3
RANGE_200mW = 4
RANGE_200uW_AUTO = 5
RANGE_2mW_AUTO = 6
RANGE_20mW_AUTO = 7
RANGE_200mW_AUTO = 8

RANGE_MAX_W = {
    1: 200e-6,
    2: 2e-3,
    3: 20e-3,
    4: 200e-3,
}

# Status Byte 3, bits 7:5 -> effectively selected range.
STATUS3_RANGE_MAP = {
    0b000: None,     # OFF, no range selected
    0b001: 1,         # 200 uW
    0b010: 2,         # 2 mW
    0b011: 3,         # 20 mW
    0b100: 4,         # 200 mW
    0b111: "error",  # error: multiple ranges selected
}

CAL_HEATER_OFF = 0
CAL_HEATER_100uW = 1
CAL_HEATER_1mW = 2
CAL_HEATER_10mW = 3
CAL_HEATER_100mW = 4

SET_ZERO = (b"S", b"Z")
SET_CALIBRATE = (b"S", b"C")

SET_RANGE = {
    RANGE_200uW: (b"R", b"1"),
    RANGE_2mW: (b"R", b"2"),
    RANGE_20mW: (b"R", b"3"),
    RANGE_200mW: (b"R", b"4"),
    RANGE_200uW_AUTO: (b"R", b"5"),
    RANGE_2mW_AUTO: (b"R", b"6"),
    RANGE_20mW_AUTO: (b"R", b"7"),
    RANGE_200mW_AUTO: (b"R", b"8"),
}

SET_CAL_HEATER = {
    CAL_HEATER_OFF: (b"C", b"0"),
    CAL_HEATER_100uW: (b"C", b"1"),
    CAL_HEATER_1mW: (b"C", b"2"),
    CAL_HEATER_10mW: (b"C", b"3"),
    CAL_HEATER_100mW: (b"C", b"4"),
}

QUERY_FIRMWARE = (b"V", b"C")
QUERY_ONE_SAMPLE = (b"D", b"1")
QUERY_STREAM = (b"D", b"S")

# High-resolution power query (last page of Appendix One):
# it is a fixed 4-byte sequence, NOT the usual !/? 8-byte format.
HIGH_RES_QUERY = bytes([38, 1, 2, 37])
HIGH_RES_OK = 0x55
HIGH_RES_ERROR = 0xAB


def build_command(sync: bytes, byte2: bytes, byte3: bytes, data: bytes = b"\x00\x00\x00\x00") -> bytes:
    """Build an 8-byte command: sync + byte2 + byte3 + 4 data bytes + CR."""
    if len(data) != 4:
        raise ValueError("data must have exactly 4 bytes")
    cmd = sync + byte2 + byte3 + data + TERMINATOR
    if len(cmd) != 8:
        raise ValueError(f"Malformed command, expected 8 bytes, got {len(cmd)}")
    return cmd


@dataclass
class Status:
    """Decoding of Status Bytes 1/2/3 (see manual, Appendix One)."""

    auto_range: bool
    cal_heater: int          # 0-4, see CAL_HEATER_* constants
    rear_cal_switch: int     # 0-4
    remote: bool
    cal_factor_ones: int
    cal_factor_decimal: int
    range_selected: Optional[Union[int, str]]
    cal_factor_sign: int     # 0 = '+', 1 = '-'
    cal_factor_tens: int

    @property
    def cal_factor_db(self) -> float:
        sign = -1 if self.cal_factor_sign else 1
        return sign * (self.cal_factor_tens * 10 + self.cal_factor_ones + self.cal_factor_decimal / 10.0)


def parse_status(status1: int, status2: int, status3: int) -> Status:
    """Decode Status Bytes 1-3 according to the PM5 manual."""
    auto_range = bool(status1 & 0b10000000)
    cal_heater = (status1 >> 4) & 0b111
    rear_cal_switch = (status1 >> 1) & 0b111
    remote = bool(status1 & 0b1)

    cal_factor_ones = (status2 >> 4) & 0b1111
    cal_factor_decimal = status2 & 0b1111

    range_bits = (status3 >> 5) & 0b111
    range_selected = STATUS3_RANGE_MAP.get(range_bits)
    cal_factor_sign = (status3 >> 4) & 0b1
    cal_factor_tens = status3 & 0b1111

    return Status(
        auto_range=auto_range,
        cal_heater=cal_heater,
        rear_cal_switch=rear_cal_switch,
        remote=remote,
        cal_factor_ones=cal_factor_ones,
        cal_factor_decimal=cal_factor_decimal,
        range_selected=range_selected,
        cal_factor_sign=cal_factor_sign,
        cal_factor_tens=cal_factor_tens,
    )


def counts_to_watts(countvalue: int, range_code: int, cal_factor_db: float = 0.0) -> float:
    """Convert a signed 16-bit raw count to power in Watts.

    Appendix One: reading = countvalue * 2 * rangemax(range) / 59576,
    then scale by 10**(cal_factor/10) if an active calibration factor is present.
    """
    rangemax = RANGE_MAX_W.get(range_code)
    if rangemax is None:
        raise ValueError(f"Unknown or invalid range code for conversion: {range_code}")
    reading = countvalue * 2.0 * rangemax / 59576.0
    if cal_factor_db:
        reading *= 10 ** (cal_factor_db / 10.0)
    return reading
