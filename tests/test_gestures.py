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
    return int(round(x * RATE))


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
        ev += feed(d, secs(0.08), gx=400.0 if i % 2 else -400.0, az=1.0)
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
