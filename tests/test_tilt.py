"""Tilt in the hand: a side lean is tilt_right / tilt_left, with repeat and re-arm."""

import math

from custom_components.triki.gestures import (
    KNOB_HOLD_S,
    TILT_CONFIRM_S,
    TILT_EVENTS,
    TILT_REPEAT_S,
    GestureDetector,
)
from custom_components.triki.protocol import Sample

from .helpers import frame

RATE = 104


def secs(x):
    return round(x * RATE)


def feed(d, n, **kw):
    out = []
    s = Sample.from_frame(frame(**kw))
    for _ in range(n):
        out.extend(d.update(s))
    return out


def lean(deg, cap_up=True):
    """Accel of a token leaned ``deg`` to the right (negative: left), held level."""
    r = math.radians(deg)
    if cap_up:  # cap up: the sensor z axis points down
        return {"ax": math.sin(r), "az": -math.cos(r)}
    return {"ax": -math.sin(r), "az": math.cos(r)}


LEVEL = lean(0)
SETTLE = secs(KNOB_HOLD_S + 0.1)  # tilt steps wait out the knob's hold too


def det(**kw):
    kw.setdefault("tilt", True)
    d = GestureDetector(RATE, knob_step_deg=30, startup_discard=0, **kw)
    feed(d, secs(0.5), **LEVEL)  # held level: armed
    return d


def tilts(events):
    return [e.type for e in events if e.type in TILT_EVENTS]


def test_a_lean_right_is_one_tilt_right():
    d = det()
    ev = feed(d, secs(TILT_CONFIRM_S + 0.1), **lean(30)) + feed(d, SETTLE, **LEVEL)
    assert tilts(ev) == ["tilt_right"]
    step = next(e for e in ev if e.type in TILT_EVENTS)
    assert step.data == {"repeat": False}


def test_a_lean_left_is_tilt_left():
    d = det()
    ev = feed(d, secs(0.35), **lean(-30)) + feed(d, SETTLE, **LEVEL)
    assert tilts(ev) == ["tilt_left"]


def test_held_lean_repeats():
    d = det()
    held = 1.5
    ev = feed(d, secs(held), **lean(35)) + feed(d, SETTLE, **LEVEL)
    want = 1 + int((held - TILT_CONFIRM_S) / TILT_REPEAT_S)
    assert tilts(ev) == ["tilt_right"] * want
    flags = [e.data["repeat"] for e in ev if e.type in TILT_EVENTS]
    assert flags == [False] + [True] * (want - 1)


def test_pcb_up_mirrors_the_sides():
    """Held PCB up with the stripe still towards the owner, right is still right."""
    d = det()
    feed(d, secs(0.5), **lean(0, cap_up=False))
    ev = feed(d, secs(0.35), **lean(30, cap_up=False)) + feed(d, SETTLE, **lean(0, cap_up=False))
    assert tilts(ev) == ["tilt_right"]


def test_no_second_step_without_levelling():
    d = det()
    ev = feed(d, secs(0.3), **lean(30))  # one step
    ev += feed(d, secs(0.3), **lean(18))  # eased back, not level
    ev += feed(d, secs(0.5), **lean(30))  # leaned again
    ev += feed(d, SETTLE, **lean(18))
    assert tilts(ev) == ["tilt_right"]
    ev = feed(d, secs(0.2), **LEVEL) + feed(d, secs(0.3), **lean(30)) + feed(d, SETTLE, **LEVEL)
    assert tilts(ev) == ["tilt_right"]


def test_short_lean_is_nothing():
    d = det()
    ev = feed(d, secs(TILT_CONFIRM_S - 0.05), **lean(30)) + feed(d, SETTLE, **LEVEL)
    assert tilts(ev) == []


def test_edge_on_is_not_a_lean():
    d = det()
    ev = feed(d, secs(2), **lean(87)) + feed(d, SETTLE, **LEVEL)
    assert tilts(ev) == []


def test_a_deep_lean_counts_and_going_deeper_keeps_it():
    """Asked for "more than 25", people lean to 70-85 (the 2026-11-23 check)."""
    d = det()
    ev = feed(d, secs(1), **LEVEL) + feed(d, secs(1), **lean(75)) + feed(d, SETTLE, **lean(75))
    assert [e.type for e in ev if e.type in TILT_EVENTS and not e.data["repeat"]] == ["tilt_right"]
    d = det()
    ev = feed(d, secs(1), **LEVEL) + feed(d, secs(0.5), **lean(50))
    ev += feed(d, secs(1), **lean(87)) + feed(d, SETTLE, **lean(50))
    assert [e.type for e in ev if e.type in TILT_EVENTS and not e.data["repeat"]] == ["tilt_right"]


def test_picked_up_leaned_needs_level_first():
    d = GestureDetector(RATE, knob_step_deg=30, startup_discard=0, tilt=True)
    ev = feed(d, secs(1), **lean(30)) + feed(d, SETTLE, **lean(30))
    assert tilts(ev) == []


def test_a_wobbling_hand_is_not_a_lean():
    d = det()
    ev = feed(d, secs(1), gy=150.0, **lean(30)) + feed(d, SETTLE, **LEVEL)
    assert tilts(ev) == []


def test_a_jolt_drops_the_held_step():
    """One motion, one gesture: a lean that ends in a shake is no step."""
    d = det()
    ev = feed(d, secs(TILT_CONFIRM_S + 0.05), **lean(30))  # step queued, not out
    ev += feed(d, 3, ax=2.5, az=-2.5) + feed(d, SETTLE, **LEVEL)
    assert tilts(ev) == []


def test_tilt_is_off_by_default():
    d = det(tilt=False)
    ev = feed(d, secs(1), **lean(30)) + feed(d, SETTLE, **LEVEL)
    assert ev == []


def test_tilt_works_with_the_knob_off():
    d = det(knob=False)
    ev = feed(d, secs(0.35), **lean(30)) + feed(d, SETTLE, **LEVEL)
    assert tilts(ev) == ["tilt_right"]


def test_invert_rotation_is_for_the_knob_only():
    """Right is right: the swap is for a knob that feels backwards, not for a lean."""
    d = det(invert_rotation=True)
    ev = feed(d, secs(0.35), **lean(30)) + feed(d, SETTLE, **LEVEL)
    assert tilts(ev) == ["tilt_right"]


def test_tilt_is_not_a_knob_step():
    """A dimmer on rotate_cw / rotate_ccw must not move on a lean."""
    d = det()
    ev = feed(d, secs(1.5), **lean(35)) + feed(d, SETTLE, **LEVEL)
    assert ev and not [e for e in ev if e.type.startswith("rotate")]
