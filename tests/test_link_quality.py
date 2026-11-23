"""Frames received against frames streamed, and the repair issue it drives."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.triki import device as device_mod
from custom_components.triki.linkquality import LinkQuality

from .conftest import connect
from .helpers import frame


def _stream(lq: LinkQuality, secs: float, rate: float, got: float, t0: float = 0.0) -> float:
    """``got`` of the frames of ``secs`` at ``rate`` arrive, evenly."""
    n = int(secs * rate * got)
    for i in range(n + 1):
        lq.frame(t0 + i * secs / n)
    return t0 + secs


def test_a_clean_stream_is_100() -> None:
    lq = LinkQuality()
    lq.start(52)
    _stream(lq, 30, 52, 1.0)
    assert lq.pct == 100.0
    assert lq.end_session() == 100.0
    assert lq.last_pct == 100.0
    assert lq.pct is None  # the next session starts empty


def test_half_the_frames_and_a_rate_switch() -> None:
    lq = LinkQuality()
    lq.start(52)
    t = _stream(lq, 20, 52, 0.5)
    lq.start(26)  # idle rate over the live link
    _stream(lq, 20, 26, 0.5, t0=t + 0.5)
    assert 49 <= lq.end_session() <= 51


def test_a_battery_pause_is_not_loss() -> None:
    lq = LinkQuality()
    lq.start(26)
    t = _stream(lq, 20, 26, 1.0)
    lq.stop()
    lq.frame(t + 0.1)  # a late frame before the restart counts nowhere
    lq.start(26)
    _stream(lq, 20, 26, 1.0, t0=t + 8)
    assert lq.end_session() == 100.0


def test_a_short_session_does_not_count() -> None:
    lq = LinkQuality()
    lq.start(52)
    _stream(lq, 5, 52, 0.2)
    assert lq.end_session() is None
    assert lq.last_pct is None
    assert lq.lossy_in_a_row == 0


def test_three_lossy_sessions_in_a_row_then_a_clean_one() -> None:
    lq = LinkQuality()
    for _ in range(2):
        lq.start(52)
        _stream(lq, 30, 52, 0.5)
        lq.end_session()
    assert not lq.lossy
    lq.start(52)
    _stream(lq, 30, 52, 0.8)  # middling: neither lossy nor clean, the run stands
    lq.end_session()
    lq.start(52)
    _stream(lq, 30, 52, 0.5)
    lq.end_session()
    assert lq.lossy
    lq.start(52)
    _stream(lq, 30, 52, 0.95)
    lq.end_session()
    assert not lq.lossy


async def test_lossy_sessions_raise_and_a_clean_one_clears_the_issue(
    hass: HomeAssistant, setup, monkeypatch
) -> None:
    dev = setup.runtime_data
    issues = ir.async_get(hass)
    issue_id = f"link_lossy_{setup.entry_id}"
    clock = [1000.0]
    monkeypatch.setattr(device_mod, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    async def session(got: float) -> None:
        _client, notify = await connect(hass, setup)
        n = int(30 * dev.stream_rate * got)
        for _ in range(n):
            clock[0] += 30 / n
            notify(None, bytearray(frame(az=-1.0)))
        dev._handle_disconnected()
        await hass.async_block_till_done()

    for _ in range(3):
        await session(0.4)
    assert issues.async_get_issue("triki", issue_id) is not None
    state = hass.states.get("sensor.triki_0000_link_quality")
    assert state is not None and 35 <= float(state.state) <= 45
    await session(1.0)
    assert issues.async_get_issue("triki", issue_id) is None
