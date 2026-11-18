"""Orientation of the token from its gyro and accelerometer.

A Madgwick filter (IMU variant, no magnetometer) turns the 6-axis stream into a
quaternion in the sensor frame: +z out of the top, the frame of the motion
frames themselves (see docs/protocol.md). Tilt (roll, pitch) is held to gravity
by the accelerometer; heading (yaw) is the integral of the gyro and drifts with
the gyro's residual offset, so it can be zeroed with :meth:`reset_heading`.

The gyro offset the gesture detector learns at rest is subtracted before the
update; the filter does not estimate its own.

Calibration (kept per token by the integration):

- ``mount``: the PCB is not exactly parallel to the cap face and a table is not
  exactly level. Lying flat, the measured gravity is rotated onto the cap's axis,
  so the token reads level on the table it was calibrated on.
- ``logo``: the angle, in the cap frame, of the edge the metal-side logo points
  to. The logo is printed on the crown, which is crimped on at any angle, so it
  is measured: with one edge lifted, gravity tells which way that edge lies.
- The heading reset then turns the pose so that this edge points away from the
  viewer (yaw 0 = "logo upright towards me").
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
# Calibration needs the token at rest: gravity within this of 1 g, little spin.
CAL_ACCEL_TOL_G = 0.08
CAL_GYRO_MAX_DPS = 8.0
CAL_FLAT_MAX_DEG = 15.0  # "lying flat" must be roughly flat
CAL_EDGE_MIN_DEG = 8.0  # a lifted edge must tilt the token at least this much
LP_ALPHA = 0.15  # low-pass on the accelerometer for calibration

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


def quat_conj(q: Quat) -> Quat:
    return (q[0], -q[1], -q[2], -q[3])


def quat_rotate(q: Quat, v: tuple[float, float, float]) -> tuple[float, float, float]:
    _, x, y, z = quat_mul(quat_mul(q, (0.0, *v)), quat_conj(q))
    return (x, y, z)


def quat_between(a: tuple[float, float, float], b: tuple[float, float, float]) -> Quat:
    """The shortest rotation taking unit vector ``a`` onto unit vector ``b``."""
    ax, ay, az = a
    bx, by, bz = b
    dot = ax * bx + ay * by + az * bz
    if dot < -0.999999:  # opposite: any axis perpendicular to a
        axis = (0.0, -az, ay) if abs(ax) < 0.9 else (-az, 0.0, ax)
        return _normalized((0.0, *axis))
    cx, cy, cz = ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx
    return _normalized((1.0 + dot, cx, cy, cz))


class CalibrationError(Exception):
    """The token is not in the pose a calibration step needs."""


def _normalized(q: Quat) -> Quat:
    n = math.sqrt(sum(c * c for c in q))
    if n == 0:
        return (1.0, 0.0, 0.0, 0.0)
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


class Orientation:
    """Madgwick IMU fusion over the token's frames."""

    def __init__(self, beta: float = BETA) -> None:
        self.beta = beta
        self.mount: Quat = (1.0, 0.0, 0.0, 0.0)  # cap frame -> sensor frame
        self.logo: float | None = None  # radians, in the cap frame
        self.reset()

    def reset(self) -> None:
        """Forget the pose; the next frames converge from the accelerometer."""
        self._q: Quat = (1.0, 0.0, 0.0, 0.0)
        self._heading: Quat = (1.0, 0.0, 0.0, 0.0)  # applied on output: zeroes yaw
        self._t: float | None = None
        self._started: float | None = None
        self.samples = 0
        self._acc_lp: tuple[float, float, float] | None = None
        self._gyro_lp = 0.0

    @property
    def ready(self) -> bool:
        return self.samples > 0

    @property
    def quaternion(self) -> Quat:
        """The pose of the cap (mount applied) with the heading reset, normalised."""
        return _normalized(quat_mul(quat_mul(self._heading, self._q), self.mount))

    @property
    def euler(self) -> tuple[float, float, float]:
        return euler_deg(self.quaternion)

    def reset_heading(self) -> None:
        """Make the current heading 0; tilt is untouched.

        With a known logo angle, heading 0 means the logo's marked edge points
        to world +y (away from the viewer); otherwise it is the sensor's yaw.
        """
        pose = quat_mul(self._q, self.mount)
        if self.logo is not None:
            wx, wy, _ = quat_rotate(pose, (math.cos(self.logo), math.sin(self.logo), 0.0))
            if math.hypot(wx, wy) > 0.3:  # the edge is not pointing up or down
                self._heading = quat_about_z(math.pi / 2 - math.atan2(wy, wx))
                return
        _, _, yaw = euler_deg(pose)
        self._heading = quat_about_z(-math.radians(yaw))

    def _at_rest(self) -> tuple[float, float, float]:
        """The low-passed gravity direction (unit), if the token is still."""
        a = self._acc_lp
        if a is None:
            raise CalibrationError("no_data")
        n = math.sqrt(sum(c * c for c in a))
        if abs(n - 1.0) > CAL_ACCEL_TOL_G or self._gyro_lp > CAL_GYRO_MAX_DPS:
            raise CalibrationError("moving")
        return (a[0] / n, a[1] / n, a[2] / n)

    def calibrate_flat(self) -> None:
        """Lying flat (either side up): take the measured gravity as the cap's axis."""
        g = self._at_rest()
        up = (0.0, 0.0, 1.0 if g[2] >= 0 else -1.0)
        if math.degrees(math.acos(min(1.0, abs(g[2])))) > CAL_FLAT_MAX_DEG:
            raise CalibrationError("not_flat")
        self.mount = quat_between(up, g)

    def calibrate_edge(self) -> None:
        """One edge lifted: record which way it lies in the cap frame."""
        gx, gy, _ = quat_rotate(quat_conj(self.mount), self._at_rest())
        if math.degrees(math.asin(min(1.0, math.hypot(gx, gy)))) < CAL_EDGE_MIN_DEG:
            raise CalibrationError("not_tilted")
        # gravity (up) leans away from the lifted edge
        self.logo = math.atan2(-gy, -gx)

    def update(
        self,
        s: Sample,
        t: float,
        gyro_bias: list[float] | tuple[float, float, float] | None = None,
    ) -> None:
        """Fold in one frame taken at monotonic time ``t`` (seconds)."""
        lp = self._acc_lp
        self._acc_lp = (
            (s.ax, s.ay, s.az)
            if lp is None
            else (
                lp[0] + LP_ALPHA * (s.ax - lp[0]),
                lp[1] + LP_ALPHA * (s.ay - lp[1]),
                lp[2] + LP_ALPHA * (s.az - lp[2]),
            )
        )
        bias = gyro_bias if gyro_bias is not None else (0.0, 0.0, 0.0)
        spin = math.sqrt(sum((g - b) ** 2 for g, b in zip((s.gx, s.gy, s.gz), bias, strict=True)))
        self._gyro_lp += LP_ALPHA * (spin - self._gyro_lp)
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
