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

import gzip
import json
import pathlib

from custom_components.triki import gestures
from custom_components.triki.protocol import FrameParser, Sample

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "handling-2026-11-23.jsonl.gz"


def _knob_steps() -> dict[str, int]:
    det = gestures.GestureDetector(52, knob=True, shake=True, tilt=True)
    parser = FrameParser()
    steps = {"handling": 0, "turning": 0, "handling_tilts": 0}
    with gzip.open(FIXTURE, "rt") as fh:
        for line in fh:
            rec = json.loads(line)
            if "hex" not in rec:
                continue
            for frame in parser.push(bytes.fromhex(rec["hex"])):
                for ev in det.update(Sample.from_frame(frame), rec["t"]):
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
    assert steps["handling_tilts"] <= 2, steps
