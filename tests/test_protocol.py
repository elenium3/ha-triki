import pytest

from custom_components.triki.protocol import (
    FrameParser,
    Sample,
    led_command,
    start_command,
)

from .helpers import frame


def test_start_command_matches_known_captures():
    # 104 Hz: Żappka app / TrikiScope / Flopsstuff capture
    assert start_command(104) == bytes.fromhex("201000d007680003")
    # 52 Hz: the command used by triki-library-python
    assert start_command(52) == bytes.fromhex("201000d007340003")
    with pytest.raises(ValueError):
        start_command(12)


def test_led_command():
    assert led_command(True) == b"\x01"
    assert led_command(False) == b"\x00"


def test_sample_scaling_and_button():
    s = Sample.from_frame(frame(gz=100.0, az=1.0, button=True))
    assert s.button
    assert s.gz == pytest.approx(100.0, abs=0.1)
    assert s.az == pytest.approx(1.0, abs=1e-3)
    assert s.accel_mag == pytest.approx(1.0, abs=1e-3)


def test_parser_handles_split_merged_and_garbage():
    f1, f2, f3 = frame(gx=10), frame(gy=20, button=True), frame(gz=-30)
    stream = b"\x01\x02\x03" + f1 + f2 + f3
    p = FrameParser()
    out = []
    # 20-byte notifications, like the real link
    for i in range(0, len(stream), 20):
        out.extend(p.push(stream[i : i + 20]))
    assert out == [f1, f2, f3]
    assert p.dropped == 3


def test_parser_keeps_split_header():
    f = frame(gx=1)
    p = FrameParser()
    assert list(p.push(b"\xff" + f[:1])) == []
    assert list(p.push(f[1:])) == [f]
