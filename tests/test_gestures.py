import math

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
    d = det()
    ev = feed(d, 2, az=3.5) + feed(d, secs(0.5))
    assert types(ev) == ["tap"]


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
