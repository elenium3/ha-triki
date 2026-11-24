"""Orientation fusion: tilt follows gravity, heading follows the gyro."""

from __future__ import annotations

import math

import pytest

from custom_components.triki.orientation import Orientation, euler_deg, quat_about_z
from custom_components.triki.protocol import Sample

RATE = 52.0


def sample(gx=0.0, gy=0.0, gz=0.0, ax=0.0, ay=0.0, az=1.0) -> Sample:
    return Sample(gx, gy, gz, ax, ay, az, False)


def run(o: Orientation, s: Sample, seconds: float, t0: float = 0.0, bias=None) -> float:
    n = round(seconds * RATE)
    t = t0
    for i in range(n):
        t = t0 + i / RATE
        o.update(s, t, bias)
    return t + 1 / RATE


def test_flat_and_still_stays_level() -> None:
    o = Orientation()
    run(o, sample(), 3.0)
    roll, pitch, yaw = o.euler
    assert abs(roll) < 0.5
    assert abs(pitch) < 0.5
    assert abs(yaw) < 0.5


def test_starts_from_the_accelerometer_tilt() -> None:
    """Lying on its side the first frame already shows the tilt, no slow drift in."""
    o = Orientation()
    o.update(sample(ay=1.0, az=0.0), 0.0)
    roll, pitch, _ = o.euler
    assert roll == pytest.approx(90, abs=1)
    assert abs(pitch) < 1


def test_tilt_converges_to_gravity() -> None:
    o = Orientation()
    run(o, sample(), 1.0)
    # pitched 30 degrees nose up: gravity moves into -x
    a = math.radians(30)
    run(o, sample(ax=-math.sin(a), az=math.cos(a)), 4.0, t0=1.0)
    _, pitch, _ = o.euler
    assert pitch == pytest.approx(30, abs=2)


def test_turn_about_z_moves_the_heading() -> None:
    o = Orientation()
    t = run(o, sample(), 1.0)
    t = run(o, sample(gz=90.0), 1.0, t0=t)
    _, _, yaw = o.euler
    assert yaw == pytest.approx(90, abs=4)
    run(o, sample(), 1.0, t0=t)
    _, _, yaw = o.euler
    assert yaw == pytest.approx(90, abs=4)


def test_gyro_bias_is_subtracted() -> None:
    o = Orientation()
    run(o, sample(gz=2.0), 5.0, bias=[0.0, 0.0, 2.0])
    _, _, yaw = o.euler
    assert abs(yaw) < 0.5


def test_reset_heading_zeroes_only_yaw() -> None:
    o = Orientation()
    t = run(o, sample(), 1.0)
    t = run(o, sample(gz=45.0), 1.0, t0=t)
    a = math.radians(20)
    run(o, sample(ax=-math.sin(a), az=math.cos(a)), 4.0, t0=t)
    o.reset_heading()
    _, pitch, yaw = o.euler
    assert abs(yaw) < 1
    assert pitch == pytest.approx(20, abs=2)


def test_a_gap_is_not_integrated() -> None:
    """A stalled link: one frame a second later must not count as a second of spin."""
    o = Orientation()
    t = run(o, sample(), 1.0)
    o.update(sample(gz=200.0), t + 1.0)
    _, _, yaw = o.euler
    assert abs(yaw) < 1


def test_shake_does_not_tip_the_model() -> None:
    """3 g of linear acceleration is not gravity: tilt stays where it was."""
    o = Orientation()
    t = run(o, sample(), 1.0)
    run(o, sample(ax=3.0, az=1.0), 0.3, t0=t)
    roll, pitch, _ = o.euler
    assert abs(roll) < 1
    assert abs(pitch) < 1


def test_euler_of_a_pure_yaw() -> None:
    assert euler_deg(quat_about_z(math.radians(30)))[2] == pytest.approx(30)


def test_reset_forgets_everything() -> None:
    o = Orientation()
    run(o, sample(gz=90.0), 1.0)
    o.reset()
    assert not o.ready
    assert o.quaternion == (1.0, 0.0, 0.0, 0.0)


def test_flat_calibration_levels_a_tilted_mount() -> None:
    """A PCB 5 degrees off the cap face reads level after the flat step."""
    o = Orientation()
    a = math.radians(5)
    still = sample(ax=-math.sin(a), az=math.cos(a))
    run(o, still, 3.0)
    assert o.euler[1] == pytest.approx(5, abs=1)
    o.calibrate_flat()
    roll, pitch, _ = o.euler
    assert abs(roll) < 0.5
    assert abs(pitch) < 0.5


def test_flat_calibration_metal_side_up() -> None:
    o = Orientation()
    run(o, sample(az=-1.0), 3.0)
    o.calibrate_flat()
    roll, pitch, _ = o.euler
    assert abs(abs(roll) - 180) < 1
    assert abs(pitch) < 1


def test_calibration_refuses_motion_and_tilt() -> None:
    from custom_components.triki.orientation import CalibrationError

    o = Orientation()
    with pytest.raises(CalibrationError, match="no_data"):
        o.calibrate_flat()
    run(o, sample(gz=60.0), 1.0)
    with pytest.raises(CalibrationError, match="moving"):
        o.calibrate_flat()
    o = Orientation()
    run(o, sample(ay=math.sin(math.radians(40)), az=math.cos(math.radians(40))), 2.0)
    with pytest.raises(CalibrationError, match="not_flat"):
        o.calibrate_flat()


@pytest.mark.parametrize("az", [1.0, -1.0])
def test_heading_reset_points_the_front_to_minus_y(az: float) -> None:
    """After the reset the front (the dot above the Z, cap -y) lies along world -y."""
    from custom_components.triki.orientation import FRONT, quat_rotate

    o = Orientation()
    t = run(o, sample(az=az), 1.0)
    t = run(o, sample(gz=50.0 * az, az=az), 1.0, t0=t)  # turn ~50 degrees on the table
    run(o, sample(az=az), 1.0, t0=t)  # and let go
    o.calibrate_flat()
    o.reset_heading()
    wx, wy, wz = quat_rotate(o.quaternion, FRONT)
    assert wx == pytest.approx(0.0, abs=0.02)
    assert wy == pytest.approx(-1.0, abs=0.02)
    roll, pitch, _ = o.euler
    assert abs(pitch) < 1
    assert abs(abs(roll) - (0 if az > 0 else 180)) < 1


def test_replayed_full_turns_read_one_revolution() -> None:
    """Real hand turns (fixture of the knob tests): yaw changes by one revolution.

    Each turn ends against a pen mark by hand, so +-25 degrees; at rest it stays put.
    """
    import gzip
    import json
    import pathlib

    from custom_components.triki import gestures
    from custom_components.triki.protocol import FrameParser

    fixture = pathlib.Path(__file__).parent / "fixtures" / "slow-turns-2026-11-18.jsonl.gz"
    parser = FrameParser()
    det = gestures.GestureDetector(52, knob_step_deg=30.0)
    o = Orientation()
    track: list[tuple[float, float]] = []  # (t, unwrapped yaw)
    last = None
    unwrap = 0.0
    with gzip.open(fixture, "rt") as fh:
        for line in fh:
            rec = json.loads(line)
            if "rate" in rec and "meta" not in rec:
                det.set_rate(rec["rate"])
            if "hex" not in rec:
                continue
            frames = list(parser.push(bytes.fromhex(rec["hex"])))
            for i, frame in enumerate(frames):
                s = Sample.from_frame(frame)
                t = rec["t"] - (len(frames) - 1 - i) * det.frame_period
                o.update(s, t, det.gyro_bias)
                det.update(s, t)
                yaw = o.euler[2]
                if last is not None:
                    d = yaw - last
                    unwrap += d - 360 * round(d / 360)
                last = yaw
                track.append((t, unwrap))

    def turned(lo: float, hi: float) -> float:
        inside = [y for t, y in track if lo <= t <= hi]
        return inside[-1] - inside[0]

    problems = []
    for label, lo, hi in [
        ("slow turn #1", 160.0, 181.6),
        ("slow turn #2", 189.5, 206.5),
        ("normal turn", 208.0, 225.5),
    ]:
        deg = turned(lo, hi)
        if not 335 <= abs(deg) <= 385:
            problems.append(f"{label}: {deg:.0f} deg")
    rest = turned(227.8, 236.6)
    if abs(rest) > 3:
        problems.append(f"at rest: {rest:.1f} deg")
    assert not problems, "\n".join(problems)


def test_heading_survives_a_reconnect() -> None:
    """A dozing token: after the link drops and comes back, the heading is kept."""
    o = Orientation()
    t = run(o, sample(), 1.0)
    t = run(o, sample(gz=90.0), 1.0, t0=t)  # turned ~90 degrees
    run(o, sample(), 1.0, t0=t)
    before = o.euler[2]
    assert abs(before - 90) < 5
    o.reset(keep_heading=True)
    run(o, sample(), 1.0, t0=100.0)
    assert o.euler[2] == pytest.approx(before, abs=1)
    o.reset()  # a plain reset still forgets it
    run(o, sample(), 1.0, t0=200.0)
    assert abs(o.euler[2]) < 1


def test_the_heading_is_known_only_after_an_alignment() -> None:
    """The card warns while the model's direction is a guess: from a start of
    Home Assistant until Align direction (or the flat calibration), kept over a
    reconnect, and over a link that streamed nothing."""
    o = Orientation()
    run(o, sample(), 1.0)
    assert not o.heading_known  # a restart: the heading is wherever the sensor says
    o.reset_heading()
    assert o.heading_known
    o.reset(keep_heading=True)
    o.reset(keep_heading=True)  # a link that streamed nothing in between
    assert o.heading_known
    run(o, sample(), 1.0, t0=100.0)
    assert o.heading_known
    o.reset()
    assert not o.heading_known


def test_a_link_that_streamed_nothing_keeps_the_carried_heading() -> None:
    o = Orientation()
    t = run(o, sample(), 1.0)
    t = run(o, sample(gz=90.0), 1.0, t0=t)
    run(o, sample(), 1.0, t0=t)
    before = o.euler[2]
    o.reset(keep_heading=True)
    o.reset(keep_heading=True)  # linked and dropped before the first frame
    run(o, sample(), 1.0, t0=100.0)
    assert o.euler[2] == pytest.approx(before, abs=1)
