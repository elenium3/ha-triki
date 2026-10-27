"""Replay a capture (.jsonl from triki_probe.py or the HA capture option).

    python tools/replay.py captures/xxx.jsonl [--rate 104] [--frames]

Feeds the raw notifications through the current parser + gesture detector and
prints, per marked segment, which events the detector produces now (vs. what
was recorded live). Use it to tune gestures.py thresholds against real data.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from triki_probe import G, P  # noqa: E402


def load(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capture", type=Path)
    ap.add_argument("--rate", type=int)
    ap.add_argument("--frames", action="store_true", help="dump every decoded frame")
    args = ap.parse_args()

    recs = load(args.capture)
    meta = next((r["meta"] for r in recs if "meta" in r), {})
    rate = args.rate or meta.get("rate", 104)
    print("meta:", meta)

    parser = P.FrameParser()
    det = G.GestureDetector(rate)
    seg = "(none)"
    now_ev: dict[str, Counter] = defaultdict(Counter)
    live_ev: dict[str, Counter] = defaultdict(Counter)
    frames = Counter()
    btn = Counter()
    peak = defaultdict(lambda: {"acc": 0.0, "gyro": 0.0, "acc_min": 99.0})
    first_t = last_t = None
    sizes = Counter()

    for r in recs:
        if "mark" in r:
            seg = r["mark"]
        elif "event" in r:
            live_ev[seg][r["event"]] += 1
        elif "hex" in r:
            data = bytes.fromhex(r["hex"])
            sizes[len(data)] += 1
            first_t = r["t"] if first_t is None else first_t
            last_t = r["t"]
            for fr in parser.push(data):
                s = P.Sample.from_frame(fr)
                frames[seg] += 1
                btn[seg] += s.button
                pk = peak[seg]
                pk["acc"] = max(pk["acc"], s.accel_mag)
                pk["acc_min"] = min(pk["acc_min"], s.accel_mag)
                pk["gyro"] = max(pk["gyro"], s.gyro_mag)
                if args.frames:
                    print(f"{r['t']:8.3f} {fr.hex()} g=({s.gx:.0f},{s.gy:.0f},{s.gz:.0f}) "
                          f"a=({s.ax:.2f},{s.ay:.2f},{s.az:.2f}) b={int(s.button)}")
                for ev in det.update(s):
                    now_ev[seg][ev.type] += 1
        elif r.get("disconnected"):
            print(f"disconnected at t={r['t']}")

    total = sum(frames.values())
    dur = (last_t - first_t) if first_t is not None else 0
    print(f"\nnotification sizes: {dict(sizes)}")
    print(f"frames: {total}, span {dur:.1f}s -> {total / dur if dur else 0:.1f} Hz (rate {rate}), "
          f"dropped bytes: {parser.dropped}")
    print(f"\n{'segment':14} {'frames':>6} {'btn':>4} {'|a|min':>6} {'|a|max':>6} {'|w|max':>7}  events now | live")
    order = list(dict.fromkeys([r["mark"] for r in recs if "mark" in r] + list(frames)))
    for s in order:
        pk = peak[s]
        print(f"{s:14} {frames[s]:6} {btn[s]:4} {pk['acc_min']:6.2f} {pk['acc']:6.2f} {pk['gyro']:7.0f}  "
              f"{dict(now_ev[s]) or '-'} | {dict(live_ev[s]) or '-'}")


if __name__ == "__main__":
    main()
