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
    """A lost burst: one frame half a second later must not count as 0.5 s of spin."""
    o = Orientation()
    t = run(o, sample(), 1.0)
    o.update(sample(gz=200.0), t + 0.5)
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
