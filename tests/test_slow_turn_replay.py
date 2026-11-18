"""Replay of slow hand turns through the detector.

``fixtures/slow-turns-2026-11-18.jsonl.gz`` is a capture (firmware 3.2.1-A, 52 Hz,
through an ESPHome proxy that lost almost no frames) of a labelled bench session:
two slow continuous clockwise turns of one full revolution each, a normal full
turn with regrips, then the token at rest. The gyro integrated about gravity gives
342-377 degrees per turn.

A slow hand turn dips below 15 deg/s in places. With that deadband and a 0.6 s
reset the detector reported 8 and 10 of the 12 steps of the slow turns.
"""

from __future__ import annotations

import gzip
import json
import pathlib

from custom_components.triki import gestures
from custom_components.triki.protocol import FrameParser, Sample

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "slow-turns-2026-11-18.jsonl.gz"

# label, from, to (capture seconds), expected rotate_cw steps (min, max); 12 = one turn
SEGMENTS = [
    ("slow turn #1", 160.0, 181.6, (11, 12)),
    ("slow turn #2", 189.5, 206.5, (11, 12)),
    ("normal turn", 208.0, 225.5, (10, 12)),
    ("at rest", 227.8, 236.6, (0, 0)),
]


def _replay():
    parser = FrameParser()
    det = gestures.GestureDetector(52, knob_step_deg=30.0)
    events: list[tuple[float, str, int]] = []
    with gzip.open(FIXTURE, "rt") as fh:
        for line in fh:
            rec = json.loads(line)
            if "rate" in rec and "meta" not in rec:
                det.set_rate(rec["rate"])
            if "hex" not in rec:
                continue
            for frame in parser.push(bytes.fromhex(rec["hex"])):
                for ev in det.update(Sample.from_frame(frame), rec["t"]):
                    events.append((rec["t"], ev.type, ev.data.get("steps", 1)))
    return events


def test_slow_turns_are_counted():
    events = _replay()
    problems = []
    for label, lo, hi, (want_min, want_max) in SEGMENTS:
        evs = [(k, n) for t, k, n in events if lo <= t <= hi]
        cw = sum(n for k, n in evs if k == "rotate_cw")
        other = [k for k, _n in evs if k != "rotate_cw"]
        if not want_min <= cw <= want_max:
            problems.append(f"{label}: {cw} cw steps, expected {want_min}-{want_max}")
        if other:
            problems.append(f"{label}: unexpected {other}")
    assert not problems, "\n".join(problems)
