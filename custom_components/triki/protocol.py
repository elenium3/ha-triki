"""Żabka Triki BLE protocol (pure Python, no Home Assistant imports).

Sources (community reverse engineering, not an official spec):
- https://github.com/Flopsstuff/triki (docs/guide/ble-protocol.md, imu-streaming.md)
- https://github.com/Maku-hub/TrikiScope (trikiscope/protocol.py: button bit in byte 1)
- https://github.com/woofter-wolf/triki-library-python

GATT:
  Nordic UART Service 6e400001-...
    RX   6e400002  write            host -> token commands
    TX   6e400003  notify           token -> host frames
    CTRL 6e400004  read/write       bit0 = green LED
  Battery 0x180F / 0x2A19, Device Information 0x180A.

Motion frame (14 bytes, after the 8-byte start command):
  0x22 | status | gyroX gyroY gyroZ | accelX accelY accelZ   (int16 LE each)
  status bit0 = button pressed.
  gyro  LSM6DSL +-2000 dps -> 14.286 LSB per deg/s
  accel LSM6DSL +-16 g     -> 2048 LSB per g
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from collections.abc import Iterator

NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
CTRL_UUID = "6e400004-b5a3-f393-e0a9-e50e24dcca9e"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
FIRMWARE_REV_UUID = "00002a26-0000-1000-8000-00805f9b34fb"
HARDWARE_REV_UUID = "00002a27-0000-1000-8000-00805f9b34fb"
MANUFACTURER_UUID = "00002a29-0000-1000-8000-00805f9b34fb"
MODEL_UUID = "00002a24-0000-1000-8000-00805f9b34fb"

FRAME_LEN = 14
HEADER0 = 0x22
STATUS_BYTES = frozenset({0x00, 0x01})

GYRO_LSB_PER_DPS = 14.286
ACCEL_LSB_PER_G = 2048.0

# Rates accepted by the firmware (LSM6DSL ODR steps). 12.5 Hz is rejected.
SUPPORTED_RATES = (26, 52, 104, 208)
DEFAULT_RATE = 104

_START_BASE = bytes([0x20, 0x10, 0x00, 0xD0, 0x07, 0x68, 0x00, 0x03])


def start_command(rate_hz: int = DEFAULT_RATE) -> bytes:
    """8-byte IMU start command; bytes 5-6 are the sample rate (uint16 LE)."""
    if rate_hz not in SUPPORTED_RATES:
        raise ValueError(f"unsupported rate {rate_hz}, use one of {SUPPORTED_RATES}")
    cmd = bytearray(_START_BASE)
    cmd[5:7] = struct.pack("<H", rate_hz)
    return bytes(cmd)


def led_command(on: bool) -> bytes:
    return b"\x01" if on else b"\x00"


@dataclass(frozen=True, slots=True)
class Sample:
    """One IMU sample in physical units (deg/s, g)."""

    gx: float
    gy: float
    gz: float
    ax: float
    ay: float
    az: float
    button: bool

    @classmethod
    def from_frame(cls, frame: bytes) -> Sample:
        if len(frame) < FRAME_LEN:
            raise ValueError(f"frame too short: {len(frame)}")
        gx, gy, gz, ax, ay, az = struct.unpack_from("<6h", frame, 2)
        return cls(
            gx / GYRO_LSB_PER_DPS,
            gy / GYRO_LSB_PER_DPS,
            gz / GYRO_LSB_PER_DPS,
            ax / ACCEL_LSB_PER_G,
            ay / ACCEL_LSB_PER_G,
            az / ACCEL_LSB_PER_G,
            bool(frame[1] & 0x01),
        )

    @property
    def accel_mag(self) -> float:
        return (self.ax * self.ax + self.ay * self.ay + self.az * self.az) ** 0.5

    @property
    def gyro_mag(self) -> float:
        return (self.gx * self.gx + self.gy * self.gy + self.gz * self.gz) ** 0.5


class FrameParser:
    """Reassemble 14-byte frames from BLE notification chunks, resyncing on header."""

    MAX_BUFFER = 256

    def __init__(self) -> None:
        self._buf = bytearray()
        self.dropped = 0

    def reset(self) -> None:
        self._buf.clear()

    def _find_header(self) -> int:
        buf = self._buf
        i = buf.find(HEADER0)
        while 0 <= i < len(buf) - 1:
            if buf[i + 1] in STATUS_BYTES:
                return i
            i = buf.find(HEADER0, i + 1)
        return -1

    def push(self, data: bytes | bytearray) -> Iterator[bytes]:
        self._buf.extend(data)
        while True:
            idx = self._find_header()
            if idx < 0:
                # keep a trailing 0x22 that may be half of a split header
                keep = 1 if self._buf and self._buf[-1] == HEADER0 else 0
                self.dropped += len(self._buf) - keep
                del self._buf[: len(self._buf) - keep]
                return
            if idx:
                self.dropped += idx
                del self._buf[:idx]
            if len(self._buf) < FRAME_LEN:
                if len(self._buf) > self.MAX_BUFFER:  # pragma: no cover - defensive
                    self._buf.clear()
                return
            frame = bytes(self._buf[:FRAME_LEN])
            del self._buf[:FRAME_LEN]
            yield frame
