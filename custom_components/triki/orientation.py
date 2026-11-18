"""Orientation of the token from its gyro and accelerometer.

A Madgwick filter (IMU variant, no magnetometer) turns the 6-axis stream into a
quaternion in the sensor frame: +z out of the top, the frame of the motion
frames themselves (see docs/protocol.md). Tilt (roll, pitch) is held to gravity
by the accelerometer; heading (yaw) is the integral of the gyro and drifts with
the gyro's residual offset, so it can be zeroed with :meth:`reset_heading`.

The gyro offset the gesture detector learns at rest is subtracted before the
update; the filter does not estimate its own.
"""

from __future__ import annotations

import math

from .protocol import Sample

# Filter gain: how hard the accelerometer pulls tilt back to gravity. Higher
# settles faster but lets shakes and taps jerk the model.
BETA = 0.08
# First frames after a (re)start: converge from the accelerometer quickly.
BETA_SETTLE = 2.5
SETTLE_S = 0.5
# Gaps longer than this (a lost burst, a rate switch) are not integrated.
MAX_DT_S = 0.1
# The accelerometer only corrects tilt while it reads about 1 g; during a swing
# or a tap it measures motion, not gravity.
ACCEL_TRUST_G = (0.75, 1.25)

type Quat = tuple[float, float, float, float]  # w, x, y, z


def quat_mul(a: Quat, b: Quat) -> Quat:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def quat_about_z(rad: float) -> Quat:
    return (math.cos(rad / 2), 0.0, 0.0, math.sin(rad / 2))


def euler_deg(q: Quat) -> tuple[float, float, float]:
    """Roll (about x), pitch (about y) and yaw (about z) in degrees, ZYX order."""
    w, x, y, z = q
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    sinp = max(-1.0, min(1.0, 2 * (w * y - z * x)))
    pitch = math.asin(sinp)
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


def _normalized(q: Quat) -> Quat:
    n = math.sqrt(sum(c * c for c in q))
    if n == 0:
        return (1.0, 0.0, 0.0, 0.0)
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


class Orientation:
    """Madgwick IMU fusion over the token's frames."""

    def __init__(self, beta: float = BETA) -> None:
        self.beta = beta
        self.reset()

    def reset(self) -> None:
        """Forget the pose; the next frames converge from the accelerometer."""
        self._q: Quat = (1.0, 0.0, 0.0, 0.0)
        self._heading: Quat = (1.0, 0.0, 0.0, 0.0)  # applied on output: zeroes yaw
        self._t: float | None = None
        self._started: float | None = None
        self.samples = 0

    @property
    def ready(self) -> bool:
        return self.samples > 0

    @property
    def quaternion(self) -> Quat:
        """The pose with the heading reset applied, normalised."""
        return _normalized(quat_mul(self._heading, self._q))

    @property
    def euler(self) -> tuple[float, float, float]:
        return euler_deg(self.quaternion)

    def reset_heading(self) -> None:
        """Make the current heading yaw 0; tilt is untouched."""
        _, _, yaw = euler_deg(self._q)
        self._heading = quat_about_z(-math.radians(yaw))

    def update(
        self,
        s: Sample,
        t: float,
        gyro_bias: list[float] | tuple[float, float, float] | None = None,
    ) -> None:
        """Fold in one frame taken at monotonic time ``t`` (seconds)."""
        if self._t is None or not 0 < t - self._t <= MAX_DT_S:
            # first frame or a gap: no integration step, just remember the time
            first = self._t is None
            self._t = t
            if first:
                self._started = t
                self._q = self._from_accel(s)
                self.samples = 1
            return
        dt = t - self._t
        self._t = t
        bx, by, bz = gyro_bias if gyro_bias is not None else (0.0, 0.0, 0.0)
        gx = math.radians(s.gx - bx)
        gy = math.radians(s.gy - by)
        gz = math.radians(s.gz - bz)
        settling = self._started is not None and t - self._started < SETTLE_S
        beta = BETA_SETTLE if settling else self.beta
        self._q = self._step(self._q, gx, gy, gz, s.ax, s.ay, s.az, dt, beta)
        self.samples += 1

    @staticmethod
    def _from_accel(s: Sample) -> Quat:
        """A level-heading pose whose tilt matches gravity."""
        a = math.sqrt(s.ax * s.ax + s.ay * s.ay + s.az * s.az)
        if a == 0:
            return (1.0, 0.0, 0.0, 0.0)
        roll = math.atan2(s.ay, s.az)
        pitch = math.atan2(-s.ax, math.sqrt(s.ay * s.ay + s.az * s.az))
        cr, sr = math.cos(roll / 2), math.sin(roll / 2)
        cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
        return _normalized((cr * cp, sr * cp, cr * sp, -sr * sp))

    @staticmethod
    def _step(  # noqa: PLR0917 - the filter's inputs, kept as plain floats
        q: Quat,
        gx: float,
        gy: float,
        gz: float,
        ax: float,
        ay: float,
        az: float,
        dt: float,
        beta: float,
    ) -> Quat:
        q0, q1, q2, q3 = q
        # rate of change from the gyro
        d0 = 0.5 * (-q1 * gx - q2 * gy - q3 * gz)
        d1 = 0.5 * (q0 * gx + q2 * gz - q3 * gy)
        d2 = 0.5 * (q0 * gy - q1 * gz + q3 * gx)
        d3 = 0.5 * (q0 * gz + q1 * gy - q2 * gx)
        norm = math.sqrt(ax * ax + ay * ay + az * az)
        if ACCEL_TRUST_G[0] <= norm <= ACCEL_TRUST_G[1]:
            ax, ay, az = ax / norm, ay / norm, az / norm
            # gradient descent step towards gravity (Madgwick 2010, IMU form)
            f1 = 2 * (q1 * q3 - q0 * q2) - ax
            f2 = 2 * (q0 * q1 + q2 * q3) - ay
            f3 = 2 * (0.5 - q1 * q1 - q2 * q2) - az
            s0 = -2 * q2 * f1 + 2 * q1 * f2
            s1 = 2 * q3 * f1 + 2 * q0 * f2 - 4 * q1 * f3
            s2 = -2 * q0 * f1 + 2 * q3 * f2 - 4 * q2 * f3
            s3 = 2 * q1 * f1 + 2 * q2 * f2
            sn = math.sqrt(s0 * s0 + s1 * s1 + s2 * s2 + s3 * s3)
            if sn > 0:
                d0 -= beta * s0 / sn
                d1 -= beta * s1 / sn
                d2 -= beta * s2 / sn
                d3 -= beta * s3 / sn
        return _normalized((q0 + d0 * dt, q1 + d1 * dt, q2 + d2 * dt, q3 + d3 * dt))
