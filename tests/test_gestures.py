import math

import pytest

from custom_components.triki.gestures import GestureDetector
from custom_components.triki.protocol import Sample

from .helpers import frame

RATE = 104


def feed(det, n, **kw):
    events = []
    s = Sample.from_frame(frame(**kw))
    for _ in range(n):
        events.extend(det.update(s))
    return events


def types(events):
    return [e.type for e in events]


def det():
    d = GestureDetector(RATE, knob_step_deg=30, startup_discard=0)
    feed(d, RATE // 2)  # settle flat
    return d


def secs(x):
    return round(x * RATE)


def test_static_is_quiet():
    d = det()
    assert feed(d, secs(3)) == []


def test_startup_discard():
    d = GestureDetector(RATE, startup_discard=20)
    assert feed(d, 20, az=5.0) == []  # noise ignored
    assert d.t == 0.0


def test_single_press():
    d = det()
    ev = feed(d, secs(0.1), button=True) + feed(d, secs(0.6))
    assert types(ev) == ["press"]


def test_double_press():
    d = det()
    ev = (
        feed(d, secs(0.1), button=True)
        + feed(d, secs(0.15))
        + feed(d, secs(0.1), button=True)
        + feed(d, secs(0.6))
    )
    assert types(ev) == ["double_press"]


def test_slow_double_press_within_default_window():
    d = det()
    ev = (
        feed(d, secs(0.1), button=True)
        + feed(d, secs(0.45))  # slower than the old 0.35 s window
        + feed(d, secs(0.1), button=True)
        + feed(d, secs(0.7))
    )
    assert types(ev) == ["double_press"]


def test_multi_press_window_is_configurable():
    d = GestureDetector(RATE, knob_step_deg=30, startup_discard=0, multi_press_window_s=0.3)
    feed(d, RATE // 2)
    ev = (
        feed(d, secs(0.1), button=True)
        + feed(d, secs(0.45))
        + feed(d, secs(0.1), button=True)
        + feed(d, secs(0.7))
    )
    assert types(ev) == ["press", "press"]


def test_triple_press():
    d = det()
    ev = []
    for _ in range(3):
        ev += feed(d, secs(0.1), button=True) + feed(d, secs(0.2))
    ev += feed(d, secs(0.7))
    assert types(ev) == ["triple_press"]


def test_long_press():
    d = det()
    ev = feed(d, secs(1.2), button=True) + feed(d, secs(0.6))
    assert types(ev) == ["long_press"]


def test_knob_ccw_and_cw():
    d = det()
    ev = feed(d, secs(1.0), gz=185.0)  # ~185 deg about the up axis
    assert set(types(ev)) == {"rotate_ccw"}
    assert sum(e.data["steps"] for e in ev) == 6
    ev = feed(d, secs(0.5), gz=-125.0)
    assert set(types(ev)) == {"rotate_cw"}
    assert sum(e.data["steps"] for e in ev) == 2


def test_knob_muted_while_button_down_and_shortly_after():
    d = det()
    # the token twists in the hand while the button is pressed and released
    ev = feed(d, secs(0.3), button=True, gz=185.0) + feed(d, secs(0.6), gz=185.0)
    assert types(ev) == ["press"]
    # a real turn a second after the release is reported again
    ev = feed(d, secs(0.5)) + feed(d, secs(1.0), gz=185.0)
    assert set(types(ev)) == {"rotate_ccw"}


def test_knob_ignores_slow_drift():
    d = det()
    assert feed(d, secs(10), gz=5.0) == []  # bias below deadband


def test_invert_rotation():
    d = GestureDetector(RATE, knob_step_deg=30, invert_rotation=True, startup_discard=0)
    feed(d, RATE // 2)
    assert set(types(feed(d, secs(0.5), gz=180.0))) == {"rotate_cw"}


def test_throw_and_landing_not_a_tap():
    d = det()
    ev = feed(d, secs(0.3), az=0.05) + feed(d, 2, az=4.0) + feed(d, secs(0.5))
    assert types(ev) == ["throw"]


def test_tap():
    """A finger tap on a resting token: a dip and a spike, then still again."""
    d = det()
    ev = feed(d, 1, az=0.7) + feed(d, 1, az=1.5) + feed(d, secs(0.5))
    assert types(ev) == ["tap"]


def test_tap_is_reported_once_the_token_is_still_again():
    d = det()
    assert types(feed(d, 1, az=0.7) + feed(d, 1, az=1.5)) == []  # not yet
    assert types(feed(d, secs(0.15))) == ["tap"]


def test_jolt_that_starts_a_move_is_not_a_tap():
    """Picking the token up can start with a jerk; it does not come to rest after."""
    d = det()
    ev = feed(d, 1, az=1.8) + feed(d, secs(0.6), gx=120.0, az=1.1) + feed(d, secs(0.5))
    assert "tap" not in types(ev)


def test_jolt_while_moving_is_not_a_tap():
    """Knocking the token on the table while waving it in the hand: no rest before."""
    d = det()
    ev = feed(d, secs(0.5), gx=200.0, az=1.1) + feed(d, 1, az=2.5) + feed(d, secs(0.5))
    assert "tap" not in types(ev)


def test_shake():
    d = det()
    ev = []
    for i in range(8):  # ~6 Hz wrist shake
        ev += feed(d, secs(0.08), gx=1500.0 if i % 2 else -1500.0, az=1.0)
    assert "shake" in types(ev)
    assert not any(t.startswith("rotate") for t in types(ev))


def test_flip():
    d = det()
    # rotate over (not static), then lie face down
    ev = feed(d, secs(0.3), gx=600.0, ay=0.5, az=0.0) + feed(d, secs(0.6), az=-1.0)
    assert "flip" in types(ev)


def test_pitch_roll_from_gravity():
    d = det()
    feed(d, secs(2), ax=0.0, ay=math.sin(math.radians(30)), az=math.cos(math.radians(30)))
    pitch, roll = d.pitch_roll
    assert abs(pitch) < 2
    assert abs(roll - 30) < 2


def test_motion_events_can_be_switched_off():
    d = GestureDetector(RATE, knob_step_deg=30, startup_discard=0, motion_gestures=False)
    feed(d, RATE // 2)
    ev = feed(d, 20, gx=200, ax=3.0)  # hard motion, would be tap/rotate/shake
    ev += feed(d, 60, az=0.0, ax=0.0)  # free fall
    assert not [
        e for e in ev if e.type in ("tap", "throw", "shake", "flip", "rotate_cw", "rotate_ccw")
    ]
    assert d.last_motion_t > 0  # still tracked for the idle logic


def test_single_press_is_immediate_without_multi_press():
    d = GestureDetector(RATE, startup_discard=0, multi_press=False)
    feed(d, RATE // 2)
    assert types(feed(d, secs(0.1), button=True)) == []
    assert types(feed(d, 1)) == ["press"]  # on release, no waiting window
    ev = (
        feed(d, secs(0.1), button=True)
        + feed(d, secs(0.15))
        + feed(d, secs(0.1), button=True)
        + feed(d, secs(0.6))
    )
    assert types(ev) == ["press", "press"]  # no double_press


def test_knob_only_reports_rotation():
    d = GestureDetector(RATE, knob_step_deg=30, startup_discard=0, motion_gestures=False, knob=True)
    feed(d, RATE // 2)
    ev = feed(d, secs(1.0), gz=185.0)
    assert set(types(ev)) == {"rotate_ccw"}
    ev = feed(d, 20, gx=200, ax=3.0) + feed(d, 60, az=0.0, ax=0.0)
    assert not [e for e in ev if e.type in ("tap", "throw", "shake", "flip")]


def test_knob_off_reports_no_rotation():
    d = GestureDetector(
        RATE, knob_step_deg=30, startup_discard=0, motion_gestures=False, knob=False
    )
    feed(d, RATE // 2)
    assert types(feed(d, secs(1.0), gz=185.0)) == []


def _shake(d, swings):
    ev = []
    for i in range(swings):  # ~6 Hz swings, real shakes peak at 1000-2300 dps
        ev += feed(d, secs(0.08), gx=1500.0 if i % 2 else -1500.0, az=1.0)
    return ev


def test_long_shake_is_one_event_and_next_shake_fires_again():
    d = det()
    ev = _shake(d, 26)  # one ~2 s shake
    assert types(ev).count("shake") == 1
    assert not any(t.startswith("rotate") for t in types(ev))
    ev = feed(d, secs(1.5), az=1.0)  # pause
    ev += _shake(d, 8)
    assert types(ev).count("shake") == 1


def test_hand_motion_is_not_a_shake():
    d = det()
    ev = []
    for i in range(12):  # moving the token around in the hand: 160-580 dps
        ev += feed(d, secs(0.08), gx=400.0 if i % 2 else -400.0, az=1.0)
    assert "shake" not in types(ev)


def test_shake_option_reports_only_shake():
    d = GestureDetector(
        RATE, knob_step_deg=30, startup_discard=0, motion_gestures=False, knob=False, shake=True
    )
    feed(d, RATE // 2)
    ev = []
    for i in range(8):
        ev += feed(d, secs(0.08), gx=1500.0 if i % 2 else -1500.0, az=1.0)
    assert set(types(ev)) == {"shake"}


def test_shake_off_reports_nothing():
    d = GestureDetector(
        RATE, knob_step_deg=30, startup_discard=0, motion_gestures=False, knob=False, shake=False
    )
    feed(d, RATE // 2)
    ev = []
    for i in range(8):
        ev += feed(d, secs(0.08), gx=1500.0 if i % 2 else -1500.0, az=1.0)
    assert types(ev) == []


# --- wall-clock timing: lower rates and lost frames (the proxy path) ---


def timed(rate, loss, seed, segments):
    """Feed ``segments`` of (seconds, frame kwargs) at ``rate`` with each frame lost with
    probability ``loss``; the detector sees the survivors with their arrival times."""
    import random

    rnd = random.Random(seed)  # noqa: S311
    d = GestureDetector(rate, knob_step_deg=30, startup_discard=0)
    dt = 1.0 / rate
    t = 100.0  # the clock origin is arbitrary
    for _ in range(rate // 2):  # settle flat, no losses
        t += dt
        d.update(Sample.from_frame(frame()), t)
    events = []
    for seconds, kw in segments:
        for _ in range(round(seconds * rate)):
            t += dt
            if rnd.random() < loss:
                continue
            events.extend(d.update(Sample.from_frame(frame(**kw)), t))
    return events


def swings(count, dps, seconds=0.08):
    return [(seconds, {"gx": dps if i % 2 else -dps, "az": 1.0}) for i in range(count)]


TWO_SHAKES = [*swings(26, 1500.0), (1.5, {"az": 1.0}), *swings(14, 1500.0)]  # 2.1 s, 1.1 s


@pytest.mark.parametrize(
    ("rate", "loss"), [(104, 0.5), (104, 0.7), (52, 0.5), (52, 0.7), (26, 0.5)]
)
@pytest.mark.parametrize("seed", range(5))
def test_shake_survives_low_rate_and_frame_loss(rate, loss, seed):
    ev = timed(rate, loss, seed, TWO_SHAKES)
    assert types(ev).count("shake") == 2  # one per episode, none missed
    assert not any(t.startswith("rotate") for t in types(ev))


def test_shake_at_idle_rate_with_heavy_loss_is_a_data_limit():
    """26 Hz with 70 % loss leaves ~8 frames/s: a 1.1 s shake is still mostly caught,
    and a long one never fires twice or as rotations."""
    missed = 0
    for seed in range(100):
        shakes = types(timed(26, 0.7, seed, TWO_SHAKES)).count("shake")
        assert shakes <= 2
        missed += shakes < 2
    assert missed <= 15


@pytest.mark.parametrize("rate", [52, 26])
@pytest.mark.parametrize("seed", range(5))
def test_hand_motion_with_frame_loss_is_not_a_shake(rate, seed):
    ev = timed(rate, 0.5, seed, swings(14, 400.0))
    assert "shake" not in types(ev)


@pytest.mark.parametrize("seed", range(5))
def test_static_with_frame_loss_is_quiet(seed):
    assert timed(26, 0.7, seed, [(5.0, {})]) == []


@pytest.mark.parametrize(("rate", "loss"), [(52, 0.5), (26, 0.3)])  # 26 Hz: 5 frames per press
@pytest.mark.parametrize("seed", range(5))
def test_double_press_timing_with_frame_loss(rate, loss, seed):
    ev = timed(
        rate,
        loss,
        seed,
        [(0.2, {"button": True}), (0.15, {}), (0.2, {"button": True}), (1.0, {})],
    )
    assert types(ev) == ["double_press"]


def test_timed_frames_never_step_back():
    d = GestureDetector(52, startup_discard=0)
    d.update(Sample.from_frame(frame()), 10.0)
    t0 = d.t
    d.update(Sample.from_frame(frame()), 9.0)  # a burst delivered out of pace
    assert d.t == pytest.approx(t0 + d.dt)
    d.update(Sample.from_frame(frame()), 12.0)
    assert d.t == pytest.approx(t0 + 2.0)


def test_motion_gestures_option_does_not_enable_knob_or_shake():
    d = GestureDetector(
        RATE, knob_step_deg=30, startup_discard=0, motion_gestures=True, knob=False, shake=False
    )
    feed(d, RATE // 2)
    assert types(feed(d, secs(1.0), gz=185.0)) == []
    ev = []
    for i in range(8):
        ev += feed(d, secs(0.08), gx=1500.0 if i % 2 else -1500.0, az=1.0)
    assert "shake" not in types(ev)
    feed(d, secs(0.4))  # at rest, as a tap needs
    assert "tap" in types(feed(d, 2, az=3.0) + feed(d, secs(0.3)))  # the experimental ones do work


def test_brisk_turn_back_and_forth_is_not_a_shake():
    """Turning between the fingers reverses fast about gravity; a shake swings about
    a horizontal axis and comes with a linear shock."""
    d = det()
    ev = []
    for i in range(8):
        ev += feed(d, secs(0.08), gz=1500.0 if i % 2 else -1500.0)
    assert "shake" not in types(ev)
    assert {"rotate_cw", "rotate_ccw"} & set(types(ev))  # it is a turn, and counted
    d = det()
    ev = []
    for i in range(8):  # the same reversals about gravity, but with the shock of a shake
        ev += feed(d, secs(0.08), gz=1500.0 if i % 2 else -1500.0, az=4.0)
    assert "shake" in types(ev)


def test_knob_counts_a_fast_spin_despite_its_centripetal_acceleration():
    """The IMU sits off the axis: a brisk spin reads 1.3-1.6 g while perfectly flat."""
    d = det()
    assert types(feed(d, secs(0.5), gz=720.0, az=1.5)) == ["rotate_ccw"] * 12


def test_knob_skips_swung_frames_but_keeps_the_partial_turn():
    d = det()
    assert types(feed(d, secs(0.1), gz=200.0)) == []  # 20° of a 30° step
    assert types(feed(d, 5, gz=200.0, az=2.3)) == []  # swung: these frames say nothing
    assert types(feed(d, secs(0.06), gz=200.0)) == ["rotate_ccw"]  # 20° + 12°: one step


def test_single_garbage_frame_is_not_a_turn():
    """At the 26 Hz idle rate one garbage frame of 2000 °/s would be 77°."""
    d = GestureDetector(26, knob_step_deg=30, startup_discard=0)
    feed(d, 13)
    assert types(feed(d, 1, gz=2000.0) + feed(d, 13)) == []
    # the real thing is confirmed by its second frame and loses nothing
    assert types(feed(d, 2, gz=500.0) + feed(d, 13)) == ["rotate_ccw"]  # 2 x 19°


def test_knob_is_muted_by_free_fall_and_a_hard_jolt():
    d = det()
    feed(d, secs(0.1), gz=200.0)  # 20° pending
    ev = feed(d, secs(0.1), gz=200.0, az=0.1)  # free fall: the partial turn is dropped
    ev += feed(d, secs(0.3), gz=200.0)  # and the knob stays muted for 0.5 s
    assert "rotate_ccw" not in types(ev)
    assert "rotate_ccw" in types(feed(d, secs(0.5), gz=200.0))
    feed(d, secs(1.0))
    feed(d, 1, az=4.0)  # a jolt
    assert "rotate_ccw" not in types(feed(d, secs(0.3), gz=200.0))


def test_knob_ignores_turns_with_the_token_edge_on():
    """Knocking the token edge-on against the table swings it about the vertical."""
    d = GestureDetector(RATE, knob_step_deg=30, startup_discard=0)
    feed(d, secs(2.0), ax=1.0, az=0.0)  # cap sideways: gravity along x
    assert types(feed(d, secs(1.0), gx=185.0, ax=1.0, az=0.0)) == []
