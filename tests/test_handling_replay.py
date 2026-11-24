"""Replay of a labelled session: picking the token up is not turning it.

``fixtures/handling-2026-11-23.jsonl.gz`` is a capture (firmware 3.2.1-A, 52 Hz,
through an ESPHome proxy) of the owner doing two things:

- t 5-124 s: picking the cap up off the table about ten times with different
  grips, holding it as if about to do something and putting it back, without
  turning it on purpose. Before the purity rule this made 24 knob steps.
- t 220-298 s: turning the cap on the table like a dimmer, slow and fast, both
  ways, three times; it slid on the table while turned. 37 knob steps before
  the rule.
"""

from __future__ import annotations

import dataclasses
import gzip
import json
import pathlib

from custom_components.triki import gestures
from custom_components.triki.protocol import FrameParser, Sample

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "handling-2026-11-23.jsonl.gz"


def _knob_steps(scale: float = 1.0) -> dict[str, int]:
    det = gestures.GestureDetector(52, knob=True, shake=True, tilt=True)
    parser = FrameParser()
    steps = {"handling": 0, "turning": 0, "handling_tilts": 0}
    with gzip.open(FIXTURE, "rt") as fh:
        for line in fh:
            rec = json.loads(line)
            if "hex" not in rec:
                continue
            for frame in parser.push(bytes.fromhex(rec["hex"])):
                s = Sample.from_frame(frame)
                if scale != 1.0:
                    s = dataclasses.replace(s, ax=s.ax * scale, ay=s.ay * scale, az=s.az * scale)
                for ev in det.update(s, rec["t"]):
                    if ev.type in gestures.TILT_EVENTS and not ev.data["repeat"]:
                        if 5 <= rec["t"] <= 124:
                            steps["handling_tilts"] += 1
                        continue
                    if not ev.type.startswith("rotate"):
                        continue
                    if 5 <= rec["t"] <= 124:
                        steps["handling"] += ev.data["steps"]
                    elif 220 <= rec["t"] <= 298:
                        steps["turning"] += ev.data["steps"]
    return steps


def test_picking_up_is_not_turning() -> None:
    steps = _knob_steps()
    assert steps["handling"] <= 3, steps
    assert steps["turning"] >= 34, steps
    # tilt in the hand on: about ten pick-ups lean the cap now and then
    assert steps["handling_tilts"] <= 1, steps


CHECK = pathlib.Path(__file__).parent / "fixtures" / "check-handle-lean-2026-11-23.jsonl.gz"


def test_a_pick_up_over_the_edge_is_not_a_lean() -> None:
    """The guided check of 2026-11-23 23:52 (52 Hz, firmware 3.2.1-A):

    - t 5-55 s: the pick-up step, five pick-ups; twice the cap was turned nearly
      over and back on the way up and came to rest leaned 28-38° in the hand,
      which made a lean each time before the over-the-edge rule;
    - t 55-90 s: the lean step, three leans each way, which made 3 right and 3
      left.
    """
    det = gestures.GestureDetector(52, knob=True, shake=True, tilt=True)
    parser = FrameParser()
    leans: dict[str, list[str]] = {"handle": [], "lean": []}
    with gzip.open(CHECK, "rt") as fh:
        for line in fh:
            rec = json.loads(line)
            if "hex" not in rec:
                continue
            for frame in parser.push(bytes.fromhex(rec["hex"])):
                for ev in det.update(Sample.from_frame(frame), rec["t"]):
                    if ev.type in gestures.TILT_EVENTS and not ev.data["repeat"]:
                        leans["handle" if rec["t"] < 55 else "lean"].append(ev.type[5])
    assert leans["handle"] == [], leans
    assert leans["lean"] == ["r", "l", "r", "l", "r", "l"], leans


PICKUP = pathlib.Path(__file__).parent / "fixtures" / "pickup-edge-2026-11-24.jsonl.gz"


def test_a_pick_up_on_the_edge_leaves_no_knob_steps() -> None:
    """The check of 2026-11-24 00:27 (52 Hz, firmware 3.2.1-A): at t 124.7 s the
    cap was picked up off the table with a jerk that stood it on its edge (82°,
    600 °/s), then wobbled level in the hand until it was put down at 128 s. The
    wobble made 3 knob steps before the lift rule."""
    det = gestures.GestureDetector(52, knob=True, shake=True, tilt=True)
    parser = FrameParser()
    steps = 0
    with gzip.open(PICKUP, "rt") as fh:
        for line in fh:
            rec = json.loads(line)
            if "hex" not in rec:
                continue
            for frame in parser.push(bytes.fromhex(rec["hex"])):
                for ev in det.update(Sample.from_frame(frame), rec["t"]):
                    if ev.type in gestures.KNOB_EVENTS and 100 <= rec["t"] <= 135:
                        steps += ev.data["steps"]
    assert steps == 0


def test_a_cap_that_reads_a_little_high_keeps_its_knob() -> None:
    """The same session as read by a cap whose accelerometer is 8 % high (1.08 g
    lying still). With the at-rest tolerance at 0.05 g the gyro offset was never
    learned, the knob stayed silent after the first pick-up and all 35 turns on
    the table were lost."""
    plain, high = _knob_steps(), _knob_steps(1.08)
    assert high["turning"] == plain["turning"], (plain, high)
    assert high["handling"] <= plain["handling"], (plain, high)
