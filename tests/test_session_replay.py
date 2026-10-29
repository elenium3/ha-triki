"""Replay of a hardware session through the detector.

``fixtures/session-2026-10-29.jsonl.gz`` is a capture (firmware 3.2.1-A through
an ESPHome proxy at 52 Hz) trimmed to the labelled parts of the session: the
token at rest, turned over by hand, picked up three times without turning,
tapped five times with a finger on the table, knocked edge-on against the table
while held, spun back and forth on the table, picked up, shaken four times and
tossed three times (plus one drop). The bounds below are what the detector made
of it when the rules were tuned; a change that moves them is worth a look.

The turning yield compares the steps reported with the angle integrated about
the gravity axis while the button is up. A stepped knob never reaches 100 %:
the remainder is dropped at every reversal and after every pause.
"""

from __future__ import annotations

import gzip
import json
import pathlib

from custom_components.triki import gestures
from custom_components.triki.protocol import FrameParser, Sample

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "session-2026-10-29.jsonl.gz"
KNOB_STEP = 30.0

# label, from, to, expectations: event -> (min, max); "yaw" -> minimum yield
SEGMENTS = [
    ("at rest", 1, 16, {"*": (0, 0)}),
    ("turned over by hand", 16.5, 19.6, {"flip": (1, 1), "rotate": (0, 0), "tap": (0, 0)}),
    ("at rest again", 20, 48, {"*": (0, 0)}),
    ("picked up x3, no turn", 90, 115, {"*": (0, 0)}),
    ("finger taps x5", 163, 176, {"tap": (4, 5), "rotate": (0, 1), "shake": (0, 0)}),
    ("knocked edge-on x5", 265, 285, {"shake": (0, 0), "throw": (0, 0), "rotate": (0, 3)}),
    ("spun on the table", 689, 752, {"yaw": 0.8, "shake": (0, 0), "tap": (0, 0), "throw": (0, 0)}),
    ("picked up and turned", 921, 927.5, {"tap": (0, 0), "shake": (0, 0)}),
    (
        "shaken x4",
        927.5,
        936.5,
        {"shake": (3, 4), "tap": (0, 0), "throw": (0, 0), "rotate": (0, 1)},
    ),
    ("tossed x3 + dropped", 936.5, 948.5, {"throw": (3, 5), "tap": (0, 0), "rotate": (0, 2)}),
]


def _replay():
    parser = FrameParser()
    det = gestures.GestureDetector(52, knob_step_deg=KNOB_STEP, motion_gestures=True)
    events: list[tuple[float, str, dict]] = []
    yaw: list[tuple[float, float, bool]] = []  # t, signed degrees about gravity, button
    with gzip.open(FIXTURE, "rt") as fh:
        for line in fh:
            rec = json.loads(line)
            if "hex" not in rec:
                continue
            for frame in parser.push(bytes.fromhex(rec["hex"])):
                s = Sample.from_frame(frame)
                for ev in det.update(s, rec["t"]):
                    events.append((rec["t"], ev.type, ev.data))
                if det.gravity is not None:
                    rate = gestures._dot((s.gx, s.gy, s.gz), det.gravity)
                    yaw.append((rec["t"], rate * det.dt, s.button))
    return events, yaw


def _steps(evs, kind):
    return sum(d.get("steps", 1) for _t, k, d in evs if k == kind)


def test_hardware_session():
    events, yaw = _replay()
    assert events, "the fixture produced no events at all"
    problems = []
    for label, lo, hi, expected in SEGMENTS:
        evs = [(t, k, d) for t, k, d in events if lo <= t <= hi]
        counts: dict[str, int] = {}
        for _t, k, d in evs:
            key = "rotate" if k.startswith("rotate") else k
            counts[key] = counts.get(key, 0) + (d.get("steps", 1) if key == "rotate" else 1)
        for key, want in expected.items():
            if key == "yaw":
                ccw_deg = sum(d for t, d, b in yaw if lo <= t <= hi and d > 0 and not b)
                cw_deg = -sum(d for t, d, b in yaw if lo <= t <= hi and d < 0 and not b)
                ccw = _steps(evs, "rotate_ccw") / max(ccw_deg / KNOB_STEP, 1)
                cw = _steps(evs, "rotate_cw") / max(cw_deg / KNOB_STEP, 1)
                if min(ccw, cw) < want or max(ccw, cw) > 1.1:
                    problems.append(f"{label}: turning yield ccw {ccw:.0%}, cw {cw:.0%}")
                continue
            got = sum(counts.values()) if key == "*" else counts.get(key, 0)
            if not want[0] <= got <= want[1]:
                problems.append(f"{label}: {key}={got}, wanted {want[0]}..{want[1]} ({counts})")
    assert not problems, "\n".join(problems)
