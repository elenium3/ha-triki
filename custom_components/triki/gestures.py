"""Gesture / button / knob detection from Triki IMU samples (pure Python).

Timing is derived from the sample count and the configured stream rate, not from
wall-clock arrival time, because BLE delivers frames in bursts.

Event types produced:
  press, double_press, triple_press, long_press   - built-in button
  rotate_cw, rotate_ccw                           - knob-style turn around the
                                                    vertical axis (data: steps, degrees)
  shake, tap, throw, flip                         - motion gestures

Thresholds are first guesses based on LSM6DSL ranges and TrikiScope's detector;
tune them via the constants or the integration options.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .protocol import Sample

# --- button ---
LONG_PRESS_S = 0.8
MULTI_PRESS_WINDOW_S = 0.35

# --- motion ---
STARTUP_DISCARD = 20          # first frames after stream start are noise
TAP_G = 2.5                   # |a| spike
THROW_G = 0.35                # |a| below this = free fall
THROW_MIN_S = 0.06
SHAKE_DPS = 150.0             # per-axis magnitude counted as a swing
SHAKE_WINDOW_S = 0.8
SHAKE_REVERSALS = 4           # sign changes of one axis within the window
FLIP_STABLE_S = 0.3
STATIC_ACCEL_TOL = 0.15       # g
STATIC_GYRO_DPS = 30.0
KNOB_DEADBAND_DPS = 15.0      # below this the turn accumulator is not fed
KNOB_RESET_S = 0.6            # idle time after which a partial turn is dropped
GRAVITY_ALPHA = 0.08          # low-pass for the gravity estimate

REFRACTORY_S = {
    "tap": 0.3,
    "throw": 1.0,
    "shake": 1.0,
    "flip": 0.8,
}


@dataclass(slots=True)
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)


def _unit(x: float, y: float, z: float) -> tuple[float, float, float] | None:
    n = math.sqrt(x * x + y * y + z * z)
    if n < 1e-6:
        return None
    return (x / n, y / n, z / n)


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


class GestureDetector:
    def __init__(
        self,
        rate_hz: int,
        knob_step_deg: float = 30.0,
        invert_rotation: bool = False,
        startup_discard: int = STARTUP_DISCARD,
    ) -> None:
        self.dt = 1.0 / rate_hz
        self.knob_step = knob_step_deg
        self.invert_rotation = invert_rotation
        self._startup_discard = startup_discard
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self) -> None:
        self.t = 0.0
        self._skip = self._startup_discard
        # button
        self.button = False
        self._down_t = 0.0
        self._long_fired = False
        self._clicks = 0
        self._last_release_t = 0.0
        # gravity / orientation
        self.gravity: tuple[float, float, float] | None = None
        self._ref_up: tuple[float, float, float] | None = None
        self._flip_since: float | None = None
        # knob
        self._turn_acc = 0.0
        self._turn_idle_since = 0.0
        # free fall
        self._ff_since: float | None = None
        # shake: per axis list of (t, sign) swings
        self._swings: list[list[tuple[float, int]]] = [[], [], []]
        self._last: dict[str, float] = {}
        self.last_motion_t = 0.0

    def _cooldown_ok(self, kind: str) -> bool:
        last = self._last.get(kind)
        return last is None or self.t - last >= REFRACTORY_S.get(kind, 0.0)

    def _fire(self, out: list[Event], kind: str, **data: Any) -> None:
        self._last[kind] = self.t
        out.append(Event(kind, data))

    # ---------------------------------------------------------------- derived
    @property
    def pitch_roll(self) -> tuple[float, float] | None:
        """Tilt in degrees from the gravity estimate (sensor frame, z = cap normal)."""
        if self.gravity is None:
            return None
        x, y, z = self.gravity
        pitch = math.degrees(math.atan2(-x, math.sqrt(y * y + z * z)))
        roll = math.degrees(math.atan2(y, z))
        return pitch, roll

    # ------------------------------------------------------------------- main
    def update(self, s: Sample) -> list[Event]:
        out: list[Event] = []
        if self._skip > 0:
            self._skip -= 1
            # keep the button edge state honest even while discarding
            self.button = s.button
            return out
        self.t += self.dt
        self._button(s.button, out)
        self._motion(s, out)
        return out

    def flush(self) -> list[Event]:
        """Emit pending multi-press on disconnect."""
        out: list[Event] = []
        if self._clicks:
            self._emit_clicks(out)
        return out

    # ----------------------------------------------------------------- button
    def _emit_clicks(self, out: list[Event]) -> None:
        kind = {1: "press", 2: "double_press"}.get(self._clicks, "triple_press")
        out.append(Event(kind, {"count": self._clicks}))
        self._clicks = 0

    def _button(self, pressed: bool, out: list[Event]) -> None:
        if pressed and not self.button:
            self._down_t = self.t
            self._long_fired = False
        elif pressed and self.button:
            if not self._long_fired and self.t - self._down_t >= LONG_PRESS_S:
                self._long_fired = True
                self._clicks = 0
                out.append(Event("long_press", {}))
        elif not pressed and self.button:
            if not self._long_fired:
                self._clicks += 1
                self._last_release_t = self.t
        elif self._clicks and self.t - self._last_release_t > MULTI_PRESS_WINDOW_S:
            self._emit_clicks(out)
        self.button = pressed

    # ----------------------------------------------------------------- motion
    def _motion(self, s: Sample, out: list[Event]) -> None:
        a = s.accel_mag
        static = abs(a - 1.0) < STATIC_ACCEL_TOL and s.gyro_mag < STATIC_GYRO_DPS
        if not static:
            self.last_motion_t = self.t

        # gravity estimate: only trust accel when it is close to 1 g
        if abs(a - 1.0) < 0.3:
            u = _unit(s.ax, s.ay, s.az)
            if u is not None:
                if self.gravity is None:
                    self.gravity = u
                else:
                    k = GRAVITY_ALPHA
                    self.gravity = _unit(
                        self.gravity[0] + k * (u[0] - self.gravity[0]),
                        self.gravity[1] + k * (u[1] - self.gravity[1]),
                        self.gravity[2] + k * (u[2] - self.gravity[2]),
                    ) or self.gravity

        # throw / free fall
        if a < THROW_G:
            if self._ff_since is None:
                self._ff_since = self.t
            elif self.t - self._ff_since >= THROW_MIN_S and self._cooldown_ok("throw"):
                self._fire(out, "throw")
                self._last["tap"] = self.t + 0.5  # suppress landing impact
        else:
            self._ff_since = None

        # tap / impact
        if a > TAP_G and self._cooldown_ok("tap") and self._cooldown_ok("throw"):
            self._fire(out, "tap", g=round(a, 2))

        # shake: count sign reversals of strong swings per axis
        shaking = False
        for i, w in enumerate((s.gx, s.gy, s.gz)):
            swings = self._swings[i]
            while swings and self.t - swings[0][0] > SHAKE_WINDOW_S:
                swings.pop(0)
            if abs(w) > SHAKE_DPS:
                sign = 1 if w > 0 else -1
                if not swings or swings[-1][1] != sign:
                    swings.append((self.t, sign))
            if len(swings) > SHAKE_REVERSALS:
                shaking = True
        if shaking and self._cooldown_ok("shake"):
            self._fire(out, "shake")
            for sw in self._swings:
                sw.clear()
            self._turn_acc = 0.0

        # knob: rotation rate about the vertical (gravity) axis
        if self.gravity is not None and not shaking:
            rate = _dot((s.gx, s.gy, s.gz), self.gravity)
            if self.invert_rotation:
                rate = -rate
            if abs(rate) >= KNOB_DEADBAND_DPS:
                if rate * self._turn_acc < 0:  # direction reversed: drop remainder
                    self._turn_acc = 0.0
                self._turn_acc += rate * self.dt
                self._turn_idle_since = self.t
            elif self.t - self._turn_idle_since > KNOB_RESET_S:
                self._turn_acc = 0.0
            steps = int(abs(self._turn_acc) // self.knob_step)
            if steps:
                # gravity unit points "up" (accel reads +1 g when flat), so a
                # positive rate is counter-clockwise viewed from above.
                kind = "rotate_ccw" if self._turn_acc > 0 else "rotate_cw"
                deg = math.copysign(steps * self.knob_step, self._turn_acc)
                self._turn_acc -= deg
                out.append(Event(kind, {"steps": steps, "degrees": abs(deg)}))

        # flip: stable orientation opposite to the reference
        if static:
            u = _unit(s.ax, s.ay, s.az)
            if u is not None:
                if self._ref_up is None:
                    self._ref_up = u
                elif _dot(u, self._ref_up) < -0.5:
                    if self._flip_since is None:
                        self._flip_since = self.t
                    elif self.t - self._flip_since >= FLIP_STABLE_S:
                        if self._cooldown_ok("flip"):
                            self._fire(out, "flip")
                        self._ref_up = u
                        self._flip_since = None
                else:
                    self._flip_since = None
                    if _dot(u, self._ref_up) > 0.8:
                        self._ref_up = u
        else:
            self._flip_since = None
