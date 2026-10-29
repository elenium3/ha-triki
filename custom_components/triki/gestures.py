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
MULTI_PRESS_WINDOW_S = 0.5

# --- motion ---
STARTUP_DISCARD = 20  # first frames after stream start are noise
TAP_G = 2.5  # |a| spike
THROW_G = 0.35  # |a| below this = free fall
THROW_MIN_S = 0.06
SHAKE_DPS = 600.0  # per-axis rate counted as a swing (hand motion 160-580, shakes 1000+)
SHAKE_WINDOW_S = 0.8
SHAKE_REVERSALS = 4  # sign changes of one axis within the window
SHAKE_QUIET_S = 1.0  # no strong swing this long ends a shake episode
FLIP_STABLE_S = 0.3
STATIC_ACCEL_TOL = 0.15  # g
STATIC_GYRO_DPS = 30.0
# A still token streams occasional garbage frames (a lost BLE packet desyncs the
# parser, which re-syncs on a stray 0x22 and decodes nonsense: |a| far from 1 g or
# a huge gyro spike). These are almost always single, isolated frames, while real
# motion lasts many frames. Only count motion that persists this long, so a glitch
# does not keep resetting the idle timer and hold the link open forever.
MOTION_CONFIRM_S = 0.1
KNOB_DEADBAND_DPS = 15.0  # below this the turn accumulator is not fed
KNOB_RESET_S = 0.6  # idle time after which a partial turn is dropped
# Pressing the button twists the token in the hand: on hardware every press came
# with 3-5 spurious rotate events within ~0.7 s. The knob is muted while the button
# is down and for this long after it is released.
KNOB_BUTTON_GUARD_S = 0.8
GRAVITY_ALPHA = 0.08  # low-pass for the gravity estimate

KNOB_EVENTS = frozenset({"rotate_cw", "rotate_ccw"})
MOTION_EVENTS = frozenset({"rotate_cw", "rotate_ccw", "shake", "tap", "throw", "flip"})

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
        *,
        knob_step_deg: float = 30.0,
        invert_rotation: bool = False,
        startup_discard: int = STARTUP_DISCARD,
        multi_press_window_s: float = MULTI_PRESS_WINDOW_S,
        motion_gestures: bool = True,
        multi_press: bool = True,
        knob: bool = True,
        shake: bool = True,
    ) -> None:
        self.dt = 1.0 / rate_hz
        self.knob_step = knob_step_deg
        self.invert_rotation = invert_rotation
        self._startup_discard = startup_discard
        self.multi_press_window = multi_press_window_s
        self.motion_gestures = motion_gestures
        self.multi_press = multi_press
        self.knob = knob
        self.shake = shake
        self.reset()

    # ------------------------------------------------------------------ state
    def set_rate(self, rate_hz: int) -> None:
        """The stream was restarted at another rate over the live link: only retime.

        The start-up discard is not re-armed: the IMU keeps running, and a press
        made right after the switch must not be lost in a skip window.
        """
        self.dt = 1.0 / rate_hz

    def reset(self) -> None:
        self.t = 0.0
        self._skip = self._startup_discard
        # button
        self.button = False
        self._down_t = 0.0
        self._long_fired = False
        self._clicks = 0
        self._last_release_t = 0.0
        self._release_t = -KNOB_BUTTON_GUARD_S
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
        self._shake_latched = False
        self._last_swing_t = 0.0
        self._last: dict[str, float] = {}
        self.last_motion_t = 0.0
        self._motion_since: float | None = None

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
        if out:
            # all of it is still tracked (idle logic, tilt), only reporting is gated
            allowed: set[str] = set()
            if self.knob:
                allowed |= KNOB_EVENTS
            if self.shake:
                allowed.add("shake")
            if self.motion_gestures:
                allowed |= MOTION_EVENTS
            out[:] = [e for e in out if e.type not in MOTION_EVENTS or e.type in allowed]
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
            self._release_t = self.t
            if not self._long_fired:
                if self.multi_press:
                    self._clicks += 1
                    self._last_release_t = self.t
                else:
                    out.append(Event("press", {"count": 1}))
        elif self._clicks and self.t - self._last_release_t > self.multi_press_window:
            self._emit_clicks(out)
        self.button = pressed

    # ----------------------------------------------------------------- motion
    def _motion(self, s: Sample, out: list[Event]) -> None:
        a = s.accel_mag
        static = abs(a - 1.0) < STATIC_ACCEL_TOL and s.gyro_mag < STATIC_GYRO_DPS
        if static:
            self._motion_since = None
        else:
            # debounce: an isolated glitch frame must not count as motion
            if self._motion_since is None:
                self._motion_since = self.t
            if self.t - self._motion_since >= MOTION_CONFIRM_S:
                self.last_motion_t = self.t

        # gravity estimate: only trust accel when it is close to 1 g
        if abs(a - 1.0) < 0.3:
            u = _unit(s.ax, s.ay, s.az)
            if u is not None:
                if self.gravity is None:
                    self.gravity = u
                else:
                    k = GRAVITY_ALPHA
                    self.gravity = (
                        _unit(
                            self.gravity[0] + k * (u[0] - self.gravity[0]),
                            self.gravity[1] + k * (u[1] - self.gravity[1]),
                            self.gravity[2] + k * (u[2] - self.gravity[2]),
                        )
                        or self.gravity
                    )

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
        swinging = False
        for i, w in enumerate((s.gx, s.gy, s.gz)):
            swings = self._swings[i]
            while swings and self.t - swings[0][0] > SHAKE_WINDOW_S:
                swings.pop(0)
            if abs(w) > SHAKE_DPS:
                swinging = True
                sign = 1 if w > 0 else -1
                if not swings or swings[-1][1] != sign:
                    swings.append((self.t, sign))
            if len(swings) > SHAKE_REVERSALS:
                shaking = True
        # back-and-forth swings: a shake in progress, not a knob turn
        oscillating = any(len(sw) > 2 for sw in self._swings)
        if swinging:
            self._last_swing_t = self.t
        elif self._shake_latched and self.t - self._last_swing_t >= SHAKE_QUIET_S:
            self._shake_latched = False  # the episode is over, the next one may fire
        if shaking and not self._shake_latched:
            # one event per episode: a 2 s shake must not fire two or three times
            self._shake_latched = True
            self._fire(out, "shake")
            for sw in self._swings:
                sw.clear()
            self._turn_acc = 0.0

        # knob: rotation rate about the vertical (gravity) axis; shaking swings the
        # token around every axis, so the knob is muted for the whole episode
        if oscillating or self._shake_latched:
            self._turn_acc = 0.0
        elif self.button or self.t - self._release_t < KNOB_BUTTON_GUARD_S:
            self._turn_acc = 0.0  # a press twists the token: not a turn
        elif self.gravity is not None:
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
