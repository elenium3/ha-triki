"""Gesture / button / knob detection from Triki IMU samples (pure Python).

Timing: ``update(sample, t)`` takes the frame's arrival time. Through a proxy
half the frames can be lost, and counting samples would then run the clock at
half speed (a 0.3 s multi-press window becomes 0.6 s, a shake looks slow).
Without ``t`` (tools, tests) time advances by one sample period per frame.
Angles (the knob) are integrated over that clock too, not over the nominal
sample period, so lost frames do not lose degrees.

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
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .protocol import Sample

# --- button ---
LONG_PRESS_S = 0.8
MULTI_PRESS_WINDOW_S = 0.5

# --- motion ---
STARTUP_DISCARD = 20  # first frames after stream start are noise
# Tap: a jolt on a token that is otherwise at rest. At 52 Hz a finger tap on a
# token lying on a table is two frames, a dip and a spike of 1.1-1.5 g: an
# absolute threshold never sees it, the jump between consecutive frames does
# (0.8-1.6 g on hardware; picking the token up peaks at 0.65). The token must
# have been still before the jolt and be still again shortly after, which keeps
# shakes, throws, lifts and knocks made while waving the token in the hand out.
TAP_JERK_G = 0.7
TAP_REST_BEFORE_S = 0.25
TAP_JOLT_S = 0.1  # the jolt may take a few frames: the big jump is often the second
TAP_REST_AFTER_S = 0.1
TAP_CONFIRM_S = 0.4  # not still again within this long: it was not a tap
THROW_G = 0.35  # |a| below this = free fall
THROW_MIN_S = 0.06
# Shake: in the last SHAKE_WINDOW_S of wall time, enough of the frames show hard
# motion (|a| far from 1 g or a high rate) and the dominant gyro axis reverses at
# least SHAKE_REVERSALS times. Fractions survive lost frames; a reversal count of
# four did not (a 50 % loss at 52 Hz hides whole swings).
SHAKE_WINDOW_S = 0.8  # ~5 swings; 26 Hz with 70 % loss still leaves 5-7 frames
SHAKE_ACTIVE_DPS = 500.0  # moving the token in the hand peaks at 160-580, shakes at 1000+
SHAKE_ACTIVE_G = 0.6  # |a| - 1 g
# A frame whose rotation is mostly about gravity is a turn, not a swing: a brisk
# back-and-forth turn between the fingers reads 500-2000 °/s with reversals and
# on hardware fired shake three times in twenty seconds. Such a frame counts as
# a swing only with the linear shock of a real shake (5-17 g on hardware, a spin
# at most 2 g).
SHAKE_ABOUT_GRAVITY = 0.8  # |rate about gravity| / |gyro|
SHAKE_HARD_G = 2.0
SHAKE_ACTIVE_FRACTION = 0.6
SHAKE_REVERSALS = 2
SHAKE_MIN_FRAMES = 5  # fewer frames in the window say nothing
SHAKE_QUIET_S = 0.6  # no active frame this long ends a shake episode
FLIP_STABLE_S = 0.3
# Which face is up, from the accelerometer z while the token lies still (+z points
# out of the green PCB, -z out of the metal cap). Between the bands the last face
# is kept, so a token resting near a threshold does not flicker.
FACE_FLAT_G = 0.8  # |z| at least this: lying on a face
FACE_EDGE_G = 0.5  # |z| at most this: standing on its edge
FACE_STABLE_S = 0.3
FACE_CAP_UP = "cap_up"
FACE_PCB_UP = "pcb_up"
FACE_EDGE = "edge"
FACES = (FACE_CAP_UP, FACE_PCB_UP, FACE_EDGE)
STATIC_ACCEL_TOL = 0.15  # g
STATIC_GYRO_DPS = 30.0
# A still token streams occasional garbage frames (a lost BLE packet desyncs the
# parser, which re-syncs on a stray 0x22 and decodes nonsense: |a| far from 1 g or
# a huge gyro spike). These are almost always single, isolated frames, while real
# motion lasts many frames. Only count motion that persists this long, so a glitch
# does not keep resetting the idle timer and hold the link open forever.
MOTION_CONFIRM_S = 0.1
KNOB_DEADBAND_DPS = 10.0  # below this the turn accumulator is not fed
KNOB_RESET_S = 1.0  # idle time after which a partial turn is dropped
# A held-up link delivers its backlog late and at once: a gap up to this long is
# time the detector did not see, not idling. A longer silence drops the partial
# turn as before (the same bound as the pose clock's CLOCK_RESYNC_S).
KNOB_GAP_KEEP_S = 5.0
# Pressing the button twists the token in the hand: on hardware every press came
# with 3-5 spurious rotate events within ~0.7 s. The knob is muted while the button
# is down and for this long after it is released.
KNOB_BUTTON_GUARD_S = 0.8
# A frame whose |a| is this far from 1 g is skipped: the token is being swung,
# or the frame is parser garbage. The partial turn is kept (KNOB_RESET_S drops
# it if the swinging goes on). The old 0.25 g reset also caught the centripetal
# acceleration of a fast spin (the IMU sits ~15 mm off the axis: 0.6 g at
# 1100 °/s) and lost half the steps of a brisk turn on hardware.
KNOB_LIFT_G = 1.0
# A single frame above the deadband is not a turn (a garbage frame decodes as a
# huge rate): its angle counts once the next frame confirms the motion.
KNOB_CONFIRM_FRAMES = 2
# A knob is turned flat. Frames with the cap tilted more than 40° from level
# (|gravity.z| below this) are skipped: on hardware knocking the token edge-on
# against the table swung it about the vertical and made 9 steps. At 60° the
# 2026-10-29 replay still gave 2 steps for the knocks; at 40° none, while the table
# spin kept 94 % of its steps and the slow turns of 2026-11-18 all of them. Other
# Triki projects use 35° (witw2/triki-py).
KNOB_LEVEL_COS = 0.766
# A jolt this hard (a shake swing reaches 5-17 g, a hard spin at most 2 g) is not a
# turn: the partial turn is dropped and the knob is muted for a moment.
KNOB_SHOCK_G = 1.5
KNOB_SHOCK_GUARD_S = 0.5
# A shake starts as a brisk twist: on 2026-11-19 two knob steps fired 0.15-0.24 s
# before the shake was recognised. Steps are held this long and dropped when a
# shake, a jolt or free fall comes first (one motion, one gesture).
KNOB_HOLD_S = 0.3
# Picking the token up turns it too, but mostly about other axes than the vertical:
# in a labelled run (2026-11-23, tests/fixtures/handling-2026-11-23) the turning
# about gravity was 0.04-0.82 of the gyro energy in the 0.5 s before the false
# steps of ten pick-ups, and 0.86-1.00 before the wanted steps of turns on the
# table. While the share over KNOB_PURITY_WINDOW_S is below KNOB_PURITY the turn
# is not counted (the partial turn waits) and steps still held are dropped: 24
# false steps became 2, 35 of 37 wanted ones stayed, slow turns lost none.
KNOB_PURITY = 0.65
KNOB_PURITY_WINDOW_S = 0.5
# A gap longer than this between two frames counts as this long for the knob
# angle: the rate in the gap is unknown. Good links show gaps of 115-155 ms,
# rarely 340 ms; 26 Hz with heavy loss needs more than 150.
KNOB_MAX_DT_S = 0.25
GRAVITY_ALPHA = 0.08  # low-pass for the gravity estimate
# Frames per second actually received, over this much wall time. Some firmware
# ignores the requested rate (find-my-triki's game mode always streams ~100 Hz);
# a sample period taken from the request would then run the clock fast.
# A congested link delivers in bursts (17-27 frames every 0.3 s on 2026-11-17)
# that drain a backlog faster than real time, so a short window over-reads the
# rate; only a long window well above the requested rate counts as a faster
# stream.
RATE_WINDOW_S = 5.0
RATE_MIN_SPAN_S = 3.0
FAST_STREAM_FACTOR = 1.5
# Gyro zero offset, learned while the token lies still. The development unit
# reads (0.3, -2.5, -0.6) °/s at rest with 0.03-0.1 °/s of noise, stable over
# a whole session; uncorrected, -0.6 °/s about z is 36° per minute of yaw.
# "Still" is judged by how little the readings spread, not by their distance from
# the current estimate: on 2026-11-23 a first estimate taken in a steady hand was
# 3.1 °/s off, every later frame on the table was too far from it to count, and
# the card's model turned 141°/min until a restart. Lying on a table the gyro
# spreads by 0.07-0.3 °/s over half a second (1-4 LSB), a hand by degrees.
BIAS_STILL_G = 0.05  # |a| - 1 g
BIAS_SETTLE_S = 0.5  # the window that must be still before it is learned from
BIAS_SPREAD_DPS = 0.5  # per axis, max - min over the window
BIAS_RESEED_DPS = 0.5  # a still window this far from the estimate replaces it
BIAS_FAST_FRAMES = 50  # plain average for the first frames, then a slow EMA
BIAS_ALPHA = 0.002  # ~10 s at 52 Hz: a slow turn below the deadband barely moves it
BIAS_MAX_DPS = 10.0  # per axis; more is not an offset

# Tilt in the hand (the "tilt" option): the token is held level, cap up or PCB up,
# with the stripe of the card's model towards the owner, and leaned to a side.
# Heading-free like the knob: the lean is read from gravity alone, so it does not
# drift (xardag's BeatSurfer "W dloni" mode does the same with a calibrated zero).
# One tilt_right / tilt_left when the lean passes TILT_ON_DEG, then one per
# TILT_REPEAT_S while it is held (``repeat: true``); the next lean needs a return
# within TILT_OFF_DEG of level first. Own event names, not the knob's: an
# automation on the knob must not react to a lean (picking the token up leans it).
TILT_ON_DEG = 25.0
TILT_OFF_DEG = 10.0
# Beyond this the token stands on its edge or is turned over, not leaned; a lean
# that goes deeper on the same side stays a lean (no new step, no reset). 60
# missed half the leans of the 2026-11-23 check: asked for "more than 25", the
# owner leaned to 70-85. At 80 the check caught 28 of 32 leans (60: 15), for
# 16 lone leans in 233 everyday captures instead of 12.
TILT_MAX_DEG = 80.0
TILT_PITCH_MAX_DEG = 30.0  # leaned forward or back as much: not a side lean
# Held still this long at the lean before the first step.
TILT_CONFIRM_S = 0.2
TILT_REPEAT_S = 0.4
# Held, not swung: Baartek's music controller gates on 0.8-1.2 g the same way.
TILT_ACCEL_TOL_G = 0.2
TILT_STILL_DPS = 80.0
# Gravity this far on the other face's side: it went over the edge since it was
# level. Picking the token up often turns it nearly over and back, and it comes
# to rest in the hand leaned (2 false leans in the 2026-11-23 pick-up step, both
# so); a lean in the hand never passes the edge. Replay: false leans in 233
# everyday captures 16 -> 10, wanted leans of the check unchanged (28 of 32).
TILT_FLIP_Z = 0.1
TILT_EVENTS = frozenset({"tilt_left", "tilt_right"})

KNOB_EVENTS = frozenset({"rotate_cw", "rotate_ccw"})
MOTION_EVENTS = (
    frozenset({"rotate_cw", "rotate_ccw", "shake", "tap", "throw", "flip"}) | TILT_EVENTS
)
EXPERIMENTAL_EVENTS = frozenset({"tap", "throw", "flip"})  # the "motion gestures" option

# The shake recorder keeps this much of the stream before each shake (diagnostics):
# a false shake on 2026-11-18 19:21 had no capture to tell what caused it.
SHAKE_RECORD_S = 1.5

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
        tilt: bool = False,
    ) -> None:
        self.dt = 1.0 / rate_hz
        # survives reset(): a reconnect of the same token keeps its offset
        self.gyro_bias: tuple[float, float, float] | None = None
        self._bias_n = 0
        self.knob_step = knob_step_deg
        self.invert_rotation = invert_rotation
        self._startup_discard = startup_discard
        self.multi_press_window = multi_press_window_s
        self.motion_gestures = motion_gestures
        self.multi_press = multi_press
        self.knob = knob
        self.shake = shake
        self.tilt = tilt
        self.reset()

    # ------------------------------------------------------------------ state
    def set_rate(self, rate_hz: int) -> None:
        """The stream was restarted at another rate over the live link: only retime.

        The start-up discard is not re-armed: the IMU keeps running, and a press
        made right after the switch must not be lost in a skip window.
        """
        self.dt = 1.0 / rate_hz
        self._arrivals.clear()

    def reset(self) -> None:
        self.t = 0.0
        self._arrivals: deque[float] = deque()
        self._bias_win: deque[tuple[float, float, float, float]] = deque()  # t, gx, gy, gz
        self._t_origin: float | None = None  # wall time of the first timed frame
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
        self.face: str | None = None  # FACES, once the token has lain still
        self._face_cand: str | None = None
        self._face_since = 0.0
        # knob
        self._turn_acc = 0.0
        self._turn_idle_since = 0.0
        self._knob_mute_until = 0.0
        self._knob_held: list[tuple[float, Event]] = []
        # t, gyro energy, its part about gravity: how pure the recent turning is
        self._purity_win: deque[tuple[float, float, float]] = deque()
        self._turn_run = 0  # consecutive frames above the deadband
        self._turn_held = 0.0  # their angle, counted once the run is confirmed
        self._speed_deg = 0.0  # angle and time turned since the last step, for speed
        self._speed_t = 0.0
        # tilt in the hand: armed again only after a return to level
        self._tilt_armed = False
        self._tilt_dir = 0
        self._tilt_side = 0  # which face was up when it was last level
        self._tilt_next = 0.0
        # tap
        self._prev_accel: tuple[float, float, float] | None = None
        self._rest_since: float | None = None
        self._rest_end: float | None = None  # when the last long enough rest ended
        self._tap_pending: float | None = None
        # free fall
        self._ff_since: float | None = None
        # shake: (t, active, sign of the dominant gyro axis) per frame in the window
        self._shake_frames: list[tuple[float, bool, int]] = []
        self._shake_latched = False
        self._last_active_t = 0.0
        self._last: dict[str, float] = {}
        # (detector time, arrival time, |a|, |gyro|, button) of the recent frames
        self._recent: deque[tuple[float, float | None, float, float, bool]] = deque()
        self.shake_window: list[list[float | int | None]] | None = None
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
    def measured_rate(self) -> float | None:
        """Frames per second received over the last RATE_WINDOW_S of wall time."""
        arr = self._arrivals
        if len(arr) < 2 or arr[-1] - arr[0] < RATE_MIN_SPAN_S:
            return None
        return (len(arr) - 1) / (arr[-1] - arr[0])

    @property
    def frame_period(self) -> float:
        """The shortest plausible time between two frames.

        The nominal period, or less when the token streams faster than asked.
        A lossy link measures slower than nominal and keeps the nominal one.
        """
        rate = self.measured_rate
        if rate is None or rate * self.dt < FAST_STREAM_FACTOR:
            return self.dt
        return 1.0 / rate

    @property
    def pitch_roll(self) -> tuple[float, float] | None:
        """Tilt in degrees from the gravity estimate (sensor frame, z = cap normal)."""
        if self.gravity is None:
            return None
        x, y, z = self.gravity
        pitch = math.degrees(math.atan2(-x, math.sqrt(y * y + z * z)))
        roll = math.degrees(math.atan2(y, z))
        return pitch, roll

    def _update_face(self, s: Sample, static: bool) -> None:
        u = _unit(s.ax, s.ay, s.az) if static else None
        if u is None:
            self._face_cand = None
            return
        z = u[2]
        if z >= FACE_FLAT_G:
            cand: str | None = FACE_PCB_UP
        elif z <= -FACE_FLAT_G:
            cand = FACE_CAP_UP
        elif abs(z) <= FACE_EDGE_G:
            cand = FACE_EDGE
        else:
            cand = None  # in between: keep what was there
        if cand != self._face_cand:
            self._face_cand, self._face_since = cand, self.t
        elif cand is not None and self.t - self._face_since >= FACE_STABLE_S:
            self.face = cand

    # ------------------------------------------------------------------- main
    def update(self, s: Sample, t: float | None = None) -> list[Event]:
        """Feed one sample; ``t`` is its arrival time on any monotonic clock."""
        out: list[Event] = []
        if self._skip > 0:
            self._skip -= 1
            # keep the button edge state honest even while discarding
            self.button = s.button
            return out
        prev_t = self.t
        if t is None:
            self.t += self.dt
        else:
            arr = self._arrivals
            arr.append(t)
            while arr[-1] - arr[0] > RATE_WINDOW_S:
                arr.popleft()
            period = self.frame_period
            if self._t_origin is None:
                self._t_origin = t - self.t - period
            # at least one sample period per frame: a burst of buffered
            # notifications must not compress the stream into an instant
            self.t = max(self.t + period, t - self._t_origin)
        self._button(s.button, out)
        gap = self.t - prev_t
        dt = min(gap, KNOB_MAX_DT_S)
        if gap <= KNOB_GAP_KEEP_S:
            # the part of a gap past KNOB_MAX_DT_S was not seen, so it is not idle
            # time either: a slow first frame of a late backlog used to drop the
            # partial turn as if the hand had stopped for the whole gap
            self._turn_idle_since += gap - dt
        self._motion(s, out, dt, t)
        if out:
            # all of it is still tracked (idle logic, tilt), only reporting is gated
            allowed: set[str] = set()
            if self.knob:
                allowed |= KNOB_EVENTS
            if self.shake:
                allowed.add("shake")
            if self.motion_gestures:
                allowed |= EXPERIMENTAL_EVENTS
            out[:] = [
                e
                for e in out
                if e.type not in MOTION_EVENTS
                or (self.tilt if e.type in TILT_EVENTS else e.type in allowed)
            ]
        return out

    def flush(self) -> list[Event]:
        """Emit pending multi-press on disconnect."""
        out: list[Event] = [e for _t, e in self._knob_held]
        self._knob_held.clear()
        if self._clicks:
            self._emit_clicks(out)
        return out

    def _tilt(self, s: Sample, a: float, disturbed: bool) -> None:
        """Side lean in the hand.

        The knob is not muted meanwhile: a lean turns the token about a level
        axis, which has next to nothing about gravity, and a mute cost the table
        spin of the 2026-10-29 replay 4 % of its steps (its wobble reads as a lean).

        Read from the raw accelerometer of calm frames, not the gravity estimate:
        its low-pass lags a quick lean by a few tenths of a second, and handling
        the token (picking it up, knocking it) then left a stale 40° lean that
        made steps on the 2026-10-29 replay.
        """
        uz = s.az / a if a else 0.0
        if self._tilt_armed and uz * self._tilt_side < -TILT_FLIP_Z:
            self._tilt_armed = False  # over the edge since it was level: level again first
        if disturbed:
            self._tilt_armed = False  # level again first: the swing may end tilted
            self._tilt_dir = 0
            return
        calm = abs(a - 1.0) <= TILT_ACCEL_TOL_G and s.gyro_mag <= TILT_STILL_DPS
        if not calm:
            # moving: no verdict, but a pending step waits for a full calm window
            self._tilt_next = max(self._tilt_next, self.t + TILT_CONFIRM_S)
            return
        ux, uy, uz = s.ax / a, s.ay / a, s.az / a
        side = 1.0 if uz < 0 else -1.0  # PCB up mirrors left and right
        roll = math.degrees(math.atan2(side * ux, math.sqrt(uy * uy + uz * uz)))
        pitch = math.degrees(math.atan2(uy, math.sqrt(ux * ux + uz * uz)))
        if abs(roll) < TILT_OFF_DEG and abs(pitch) < TILT_PITCH_MAX_DEG:
            self._tilt_armed = True
            self._tilt_dir = 0
            self._tilt_side = 1 if uz > 0 else -1
            return
        d = 1 if roll > 0 else -1
        if abs(roll) > TILT_MAX_DEG and self._tilt_dir == d:
            return  # leaned on past the range: still the same lean
        if not (TILT_ON_DEG <= abs(roll) <= TILT_MAX_DEG and abs(pitch) <= TILT_PITCH_MAX_DEG):
            self._tilt_dir = 0
            return
        if self._tilt_dir != d:
            if not self._tilt_armed:
                return  # still the last lean, or picked up leaned
            self._tilt_dir = d
            self._tilt_next = self.t + TILT_CONFIRM_S
        if self.button or self.t - self._release_t < KNOB_BUTTON_GUARD_S:
            self._tilt_next = max(self._tilt_next, self.t + TILT_CONFIRM_S)
        elif self.t >= self._tilt_next:
            repeat = not self._tilt_armed
            self._tilt_armed = False
            self._tilt_next = self.t + TILT_REPEAT_S
            # held like the knob's steps: a shake that starts as a lean drops it
            kind = "tilt_right" if d > 0 else "tilt_left"
            self._knob_held.append((self.t, Event(kind, {"repeat": repeat})))

    def _turn_purity(self, s: Sample) -> float:
        """Share of the gyro energy about gravity over KNOB_PURITY_WINDOW_S.

        1.0 while the token hardly turns: noise says nothing about handling.
        """
        bx, by, bz = self.gyro_bias or (0.0, 0.0, 0.0)
        w = (s.gx - bx, s.gy - by, s.gz - bz)
        about = _dot(w, self.gravity) if self.gravity is not None else 0.0
        win = self._purity_win
        win.append((self.t, w[0] * w[0] + w[1] * w[1] + w[2] * w[2], about * about))
        while win and self.t - win[0][0] > KNOB_PURITY_WINDOW_S:
            win.popleft()
        total = sum(x[1] for x in win)
        if total < len(win) * KNOB_DEADBAND_DPS * KNOB_DEADBAND_DPS:
            return 1.0
        return sum(x[2] for x in win) / total

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
    def _learn_bias(self, s: Sample, a: float) -> None:
        win = self._bias_win
        g = (s.gx, s.gy, s.gz)
        if abs(a - 1.0) >= BIAS_STILL_G or max(abs(v) for v in g) > BIAS_MAX_DPS:
            win.clear()
            return
        win.append((self.t, *g))
        while self.t - win[0][0] > BIAS_SETTLE_S:
            win.popleft()
        if self.t - win[0][0] < BIAS_SETTLE_S * 0.9:
            return  # not still for long enough yet
        axes = [[f[i] for f in win] for i in (1, 2, 3)]
        if max(max(v) - min(v) for v in axes) >= BIAS_SPREAD_DPS:
            return  # moving, or held in a hand
        b = self.gyro_bias
        if b is None or math.dist([sum(v) / len(v) for v in axes], b) > BIAS_RESEED_DPS:
            # the first estimate, or a wrong one: start over from this still window
            self.gyro_bias = (
                sum(axes[0]) / len(win),
                sum(axes[1]) / len(win),
                sum(axes[2]) / len(win),
            )
            self._bias_n = len(win)
            return
        self._bias_n += 1
        k = 1.0 / self._bias_n if self._bias_n <= BIAS_FAST_FRAMES else BIAS_ALPHA

        def step(bi: float, gi: float) -> float:
            return max(-BIAS_MAX_DPS, min(BIAS_MAX_DPS, bi + k * (gi - bi)))

        self.gyro_bias = (step(b[0], g[0]), step(b[1], g[1]), step(b[2], g[2]))

    def _record(self, s: Sample, a: float, arrival: float | None) -> None:
        rec = self._recent
        rec.append((self.t, arrival, a, s.gyro_mag, s.button))
        while rec and self.t - rec[0][0] > SHAKE_RECORD_S:
            rec.popleft()

    def _snapshot(self) -> list[list[float | int | None]]:
        """The recorded frames as [s before the shake, ms since the previous arrival, |a|, |gyro|, button]."""
        out: list[list[float | int | None]] = []
        prev: float | None = None
        for t, arr, a, g, b in self._recent:
            gap = None if arr is None or prev is None else round((arr - prev) * 1000)
            prev = arr
            out.append([round(t - self.t, 3), gap, round(a, 2), round(g), int(b)])
        return out

    def _motion(self, s: Sample, out: list[Event], dt: float, arrival: float | None = None) -> None:
        a = s.accel_mag
        self._record(s, a, arrival)
        self._learn_bias(s, a)
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

        # tap: a jolt between two frames, at rest before and soon after
        accel = (s.ax, s.ay, s.az)
        prev = self._prev_accel
        self._prev_accel = accel
        if static:
            if self._rest_since is None:
                self._rest_since = self.t
        elif self._rest_since is not None:
            if self.t - self._rest_since >= TAP_REST_BEFORE_S:
                self._rest_end = self.t
            self._rest_since = None
        rested = self._rest_end is not None and self.t - self._rest_end <= TAP_JOLT_S
        if self._tap_pending is not None:
            if self.t - self._tap_pending > TAP_CONFIRM_S or a < THROW_G:
                self._tap_pending = None
            elif self._rest_since is not None and self.t - self._rest_since >= TAP_REST_AFTER_S:
                self._tap_pending = None
                if self._cooldown_ok("tap") and self._cooldown_ok("throw"):
                    self._fire(out, "tap")
        elif prev is not None and rested and not static:
            jerk = math.sqrt(
                (accel[0] - prev[0]) ** 2 + (accel[1] - prev[1]) ** 2 + (accel[2] - prev[2]) ** 2
            )
            if jerk >= TAP_JERK_G:
                self._tap_pending = self.t

        # shake: share of hard-motion frames and reversals of the dominant gyro
        # axis within a wall-clock window
        rates = (s.gx, s.gy, s.gz)
        dominant = max(range(3), key=lambda i: abs(rates[i]))
        active = abs(a - 1.0) > SHAKE_ACTIVE_G or s.gyro_mag > SHAKE_ACTIVE_DPS
        if (
            active
            and self.gravity is not None
            and abs(a - 1.0) <= SHAKE_HARD_G
            and abs(_dot(rates, self.gravity)) >= SHAKE_ABOUT_GRAVITY * s.gyro_mag
        ):
            active = False  # turning, not swinging
        sign = (1 if rates[dominant] > 0 else -1) if active else 0
        frames = self._shake_frames
        frames.append((self.t, active, sign))
        while frames and self.t - frames[0][0] > SHAKE_WINDOW_S:
            frames.pop(0)
        if active:
            self._last_active_t = self.t
        elif self._shake_latched and self.t - self._last_active_t >= SHAKE_QUIET_S:
            # the episode is over: the next one is judged on its own frames
            self._shake_latched = False
            frames.clear()
        # the window is judged from its first hard-motion frame, so the rest
        # before a shake does not delay the verdict by a whole window
        first = next((i for i, f in enumerate(frames) if f[1]), len(frames))
        episode = frames[first:]
        n_active = sum(1 for f in episode if f[1])
        reversals = 0
        last_sign = 0
        for _t, _act, sg in episode:
            if sg and last_sign and sg != last_sign:
                reversals += 1
            if sg:
                last_sign = sg
        shaking = (
            active
            and len(episode) >= SHAKE_MIN_FRAMES
            and n_active >= SHAKE_ACTIVE_FRACTION * len(episode)
            and reversals >= SHAKE_REVERSALS
        )
        if shaking and not self._shake_latched:
            # one event per episode: a 2 s shake must not fire two or three times
            self._shake_latched = True
            self.shake_window = self._snapshot()
            self._fire(out, "shake")
            frames.clear()
            self._turn_acc = 0.0

        disturbed = self._shake_latched or abs(a - 1.0) > KNOB_SHOCK_G or a < THROW_G
        if self.tilt:
            self._tilt(s, a, disturbed)

        # knob: rotation rate about the vertical (gravity) axis. Shaking swings the
        # token around every axis: a hard jolt or a latched shake drops the partial
        # turn and mutes the knob for a moment.
        purity = self._turn_purity(s)  # every frame, so the window has no gaps
        if disturbed:
            # a shake, a jolt or free fall: whatever turned was not a knob
            self._turn_acc = 0.0
            self._knob_held.clear()
            self._knob_mute_until = self.t + KNOB_SHOCK_GUARD_S
        elif self.button or self.t - self._release_t < KNOB_BUTTON_GUARD_S:
            self._turn_acc = 0.0  # a press twists the token: not a turn
        elif self.t < self._knob_mute_until:
            self._turn_acc = 0.0
        elif abs(a - 1.0) > KNOB_LIFT_G:
            pass  # being swung: this frame says nothing about turning, keep the rest
        elif self.gravity is not None and abs(self.gravity[2]) < KNOB_LEVEL_COS:
            pass  # held edge-on: handled, not turned
        elif purity < KNOB_PURITY:
            # handled, not turned: steps still held go, the partial turn waits
            self._knob_held = [(t, e) for t, e in self._knob_held if e.type in TILT_EVENTS]
        elif self.gravity is not None:
            bx, by, bz = self.gyro_bias or (0.0, 0.0, 0.0)
            rate = _dot((s.gx - bx, s.gy - by, s.gz - bz), self.gravity)
            if self.invert_rotation:
                rate = -rate
            if abs(rate) >= KNOB_DEADBAND_DPS:
                if rate * self._turn_acc < 0:  # direction reversed: drop remainder
                    self._turn_acc = 0.0
                    self._speed_deg = self._speed_t = 0.0
                self._turn_run += 1
                self._speed_deg += abs(rate) * dt
                self._speed_t += dt
                self._turn_held += rate * dt
                if self._turn_run >= KNOB_CONFIRM_FRAMES:
                    self._turn_acc += self._turn_held
                    self._turn_held = 0.0
                self._turn_idle_since = self.t
            else:
                self._turn_run = 0
                self._turn_held = 0.0
                if self.t - self._turn_idle_since > KNOB_RESET_S:
                    self._turn_acc = 0.0
                    self._speed_deg = self._speed_t = 0.0
            steps = int(abs(self._turn_acc) // self.knob_step)
            if steps:
                # gravity unit points "up" (at rest the accel reads +1 g upward), so a
                # positive rate is counter-clockwise viewed from above.
                kind = "rotate_ccw" if self._turn_acc > 0 else "rotate_cw"
                deg = math.copysign(steps * self.knob_step, self._turn_acc)
                self._turn_acc -= deg
                data: dict[str, Any] = {"steps": steps, "degrees": abs(deg)}
                if self._speed_t > 0:
                    # mean rate while turning since the last step, pauses left out
                    data["speed"] = round(self._speed_deg / self._speed_t)
                self._speed_deg = self._speed_t = 0.0
                self._knob_held.append((self.t, Event(kind, data)))
        while self._knob_held and self.t - self._knob_held[0][0] >= KNOB_HOLD_S:
            out.append(self._knob_held.pop(0)[1])

        self._update_face(s, static)

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
