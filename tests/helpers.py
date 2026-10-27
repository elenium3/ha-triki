"""Synthetic Triki frames."""

from __future__ import annotations

import struct

from custom_components.triki.protocol import ACCEL_LSB_PER_G, GYRO_LSB_PER_DPS


def frame(
    gx: float = 0.0,
    gy: float = 0.0,
    gz: float = 0.0,
    ax: float = 0.0,
    ay: float = 0.0,
    az: float = 1.0,
    button: bool = False,
) -> bytes:
    def g(v: float) -> int:
        return max(-32768, min(32767, round(v * GYRO_LSB_PER_DPS)))

    def a(v: float) -> int:
        return max(-32768, min(32767, round(v * ACCEL_LSB_PER_G)))

    return bytes([0x22, 0x01 if button else 0x00]) + struct.pack(
        "<6h", g(gx), g(gy), g(gz), a(ax), a(ay), a(az)
    )
